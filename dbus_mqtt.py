#!/usr/bin/python3 -u
# -*- coding: utf-8 -*-
import argparse
import dbus
import json
import logging
import os
import sys
from time import time
import traceback
import signal
from dbus.mainloop.glib import DBusGMainLoop
from lxml import etree
from collections import OrderedDict
from functools import partial, update_wrapper
from gi.repository import GLib

from itertools import zip_longest

# Victron packages
AppDir = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(1, os.path.join(AppDir, 'ext', 'velib_python'))
from logger import setup_logging
from ve_utils import get_vrm_portal_id, exit_on_error, wrap_dbus_value, unwrap_dbus_value, add_name_owner_changed_receiver
from mqtt_gobject_bridge import MqttGObjectBridge
from mosquitto_bridge_registrator import MosquittoBridgeRegistrator


SoftwareVersion = '1.30'
ServicePrefix = 'com.victronenergy.'
VeDbusInvalid = dbus.Array([], signature=dbus.Signature('i'), variant_level=1)
blocked_items = {('vebus', u'/Interfaces/Mk2/Tunnel'), ('paygo', '/LVD/Threshold')}

MAX_TOPIC_AGE = 60

class reify(object):
	""" Decorator for class methods. Turns the method into a property that
	    is evaluated once, and then replaces the property, effectively caching
	    it and evaluating it only once. """
	def __init__(self, wrapped):
		self.wrapped = wrapped
		update_wrapper(self, wrapped)
	def __get__(self, inst, objtype=None):
		if inst is None:
			return self
		val = self.wrapped(inst)
		setattr(inst, self.wrapped.__name__, val)
		return val

class BaseTopic(object):
	__slots__ = ('topic','timestamp', 'maxage')

	def __init__(self, maxage):
		self.timestamp = int(time())
		self.maxage = maxage

class WildcardTopic(BaseTopic):
	def __init__(self, maxage):
		super(WildcardTopic, self).__init__(maxage)
		self.topic = None

	def match(self, topic):
		return True

	def __eq__(self, other):
		return isinstance(other, WildcardTopic)

	def __hash__(self):
		return hash(None)

# payload example:
# ["system/#","inverter/+/voltage"]
# filter string can end in a # (test with "endswith"), or contain a `+`.
class Topic(BaseTopic):
	def __init__(self, t, maxage):
		super(Topic, self).__init__(maxage)
		self.topic = tuple(t)

	def match(self, topic):
		for x, y in zip_longest(self.topic, topic):
			if None in (x, y):
				return False
			if '+' in (x, y):
				continue
			if '#' in (x, y):
				return True
			if x == y:
				continue
			return False
		return True

	def __eq__(self, other):
		return self.topic == other.topic

	def __hash__(self):
		return hash('/'.join(self.topic))

class ExactTopic(Topic):
	""" This is here because it is faster for matches without
	    wildcards. """
	def match(self, topic):
		return self.topic == topic

class Subscriptions(object):
	def __init__(self):
		self.topics = []

	def subscribe_all(self, ttl=MAX_TOPIC_AGE):
		# Put it first in the list for performance reasons
		w = WildcardTopic(ttl)
		try:
			self.topics.remove(w)
		except ValueError:
			self.topics.insert(0, w)
			return w

		self.topics.insert(0, w)
		return None

	def subscribe(self, topic, ttl=MAX_TOPIC_AGE):
		t = Topic(topic.split('/'), ttl) if '+' in topic or '#' in topic else ExactTopic(topic.split('/'), ttl)
		# Removing and re-adding updates timestamp and potentially also ttl
		try:
			self.topics.remove(t)
		except ValueError:
			# topic wasn't in the list, add it
			self.topics.append(t)
			return t

		# Topic was in the list, but removed. Re-add it.
		self.topics.append(t)
		return None

	def match(self, t):
		return any(topic.match(t) for topic in self.topics)

	def cleanup(self, published, exceptions):
		""" Remove expired topics from subscriptions. Return topics that
		    should be unpublished. """
		affected_topics = set()
		now = int(time())
		expired = [t for t in self.topics if max(0, now - t.timestamp) > t.maxage]
		if expired:
			for r in expired:
				# Expire the topic
				self.topics.remove(r)

			if any(isinstance(t, WildcardTopic) for t in self.topics):
				# No need to traverse everything, they will all match
				return ()

			# Find topics that should no longer be published
			return list(filter(lambda t: not self.match(t.shorttopic), published - exceptions))

		# Nothing was expired
		return ()

# Keep track of full and short topic
class PublishedTopic(object):
	def __init__(self, fulltopic):
		self.fulltopic = fulltopic
	@reify
	def shorttopic(self):
		return tuple(self.fulltopic.split('/')[2:])
	def __eq__(self, other):
		return isinstance(other, PublishedTopic) and self.fulltopic == other.fulltopic
	def __hash__(self):
		return hash(self.fulltopic)

class DbusMqtt(MqttGObjectBridge):
	def __init__(self, mqtt_server=None, ca_cert=None, user=None, passwd=None, dbus_address=None,
				keep_alive_interval=None, init_broker=False, debug=False):
		self._dbus_address = dbus_address
		self._dbus_conn = (dbus.SessionBus() if 'DBUS_SESSION_BUS_ADDRESS' in os.environ else dbus.SystemBus()) \
			if dbus_address is None \
			else dbus.bus.BusConnection(dbus_address)
		add_name_owner_changed_receiver(self._dbus_conn, self._dbus_name_owner_changed)
		self._connected_to_cloud = False

		# @todo EV Get portal ID from com.victronenergy.system?
		self._system_id = get_vrm_portal_id()
		self._system_id_topic = PublishedTopic('N/{}/system/0/Serial'.format(
			self._system_id))
		# Key: D-BUS Service + path, value: topic
		self._topics = {}
		# Key: topic, value: last value seen on D-Bus
		self._values = {}
		# Key: service_type/device_instance, value: D-Bus service name
		self._services = {}
		# Key: short D-Bus service name (eg. 1:31), value: full D-Bus service name (eg. com.victronenergy.settings)
		self._service_ids = {}
		# Track subscriptions.
		self._subscriptions = Subscriptions()
		self._published = set()
		# A queue of value changes, so that we may rate-limit this somewhat
		self.queue = OrderedDict()
		GLib.timeout_add(1000, self._timer_service_queue)
		GLib.timeout_add(10000, self._expire_stale_topics)
		self._last_queue_run = 0

		if init_broker:
			self._registrator = MosquittoBridgeRegistrator(self._system_id)
			self._registrator.register()
		else:
			self._registrator = None

		self._dbus_conn.add_signal_receiver(self._on_dbus_value_changed,
			dbus_interface='com.victronenergy.BusItem', signal_name='PropertiesChanged', path_keyword='path',
			sender_keyword='service_id')
		self._dbus_conn.add_signal_receiver(self._on_dbus_items_changed,
			dbus_interface='com.victronenergy.BusItem',
			signal_name='ItemsChanged', path='/', sender_keyword='service_id')
		services = self._dbus_conn.list_names()
		for service in services:
			if service.startswith('com.victronenergy.'):
				self._service_ids[self._dbus_conn.get_name_owner(service)] = service
				self._scan_dbus_service(service)

		self._keep_alive_interval = keep_alive_interval
		MqttGObjectBridge.__init__(self, mqtt_server, "ve-dbus-mqtt-py", ca_cert, user, passwd, debug)

	def publish(self, topic, value):
		""" Publish to mqtt IF keepalive permits. Publish only topics that are currently alive. """
		pt = PublishedTopic(topic)
		if pt in self._published:
			self._publish(topic, value)
		elif self._subscriptions.match(pt.shorttopic):
			self._published.add(pt)
			self._publish(topic, value)

	def _publish(self, topic, value):
		# Put it into the queue
		self.queue[topic] = value

	def _unpublish(self, topic):
		# Put it into the queue
		self._published.discard(PublishedTopic(topic))
		self.queue[topic] = None

	def _publish_all(self):
		for topic in sorted(self._values.keys()):
			self.publish(topic, self._values[topic])

	def _expire_stale_topics(self):
		try:
			for pt in self._subscriptions.cleanup(self._published, {self._system_id_topic}):
				logging.debug("Expiring topic %s", pt.shorttopic)
				self._unpublish(pt.fulltopic)
		finally:
			return True

	def _on_connect(self, client, userdata, dict, rc):
		MqttGObjectBridge._on_connect(self, client, userdata, dict, rc)
		logging.info('[Connected] Result code {}'.format(rc))
		self._client.subscribe('R/{}/#'.format(self._system_id), 0)
		self._client.subscribe('W/{}/#'.format(self._system_id), 0)
		if self._registrator is not None and self._registrator.client_id is not None:
			self._client.subscribe('$SYS/broker/connection/{}/state'.format(self._registrator.client_id), 0)

		# Indicate that the new keepalive mechanism is supported
		self._publish('N/{}/keepalive'.format(self._system_id), 1)

		# Publish serial number once. It never changes, and it is retained in
		# the broker. Lower down we take care not to unpublish it (should
		# systemcalc be restarted).
		self._publish(self._system_id_topic.fulltopic, self._system_id)

		# Send all values at once, because values may have changed when we were disconnected.
		self._publish_all()

	def _on_message(self, client, userdata, msg):
		MqttGObjectBridge._on_message(self, client, userdata, msg)
		if msg.topic.startswith('$SYS/broker/connection/'):
			if int(msg.payload) == 1:
				logging.info('[Message] Connected to cloud broker')
				self._connected_to_cloud = True
			elif self._connected_to_cloud:
				# As long as we have connection with the cloud server, we do not have to worry about
				# authentication. After connection loss, we have to authenticate again, which is a nice
				# moment to initialize the broker again in case our remote_password has been reset on the
				# server, or if someone has unlinks VRM page.
				logging.error('[Message] Lost connection with cloud broker')
				self._connected_to_cloud = False
				self._registrator.register()
			return
		try:
			logging.debug('[Request] {}: {}'.format(msg.topic, str(msg.payload)))
			action, system_id, path = msg.topic.split('/', 2)
			if system_id != self._system_id:
				raise Exception('Unknown system id')
			topic = 'N/{}/{}'.format(system_id, path)
			if action == 'W':
				self._handle_write(topic, msg.payload)
			elif action == 'R':
				if path == 'system/0/Serial':
					self._handle_serial_read(topic, msg.payload)
				elif path == 'keepalive':
					self._handle_keepalive(msg.payload)
				else:
					self._handle_read(topic)
		except:
			logging.error('[Request] Error in request: {} {}'.format(msg.topic, msg.payload))
			traceback.print_exc()

	def _handle_serial_read(self, topic, payload):
		""" Currently a request for /Serial is considered a subscription for
		    backwards compatibility. """
		if self._subscriptions.subscribe_all(self._keep_alive_interval) is not None:
			self._publish(topic, self._system_id)
			self._publish_all()

	def _handle_keepalive(self, payload):
		if payload:
			topics = json.loads(payload)
			for topic in topics:
				ob = self._subscriptions.subscribe(topic, self._keep_alive_interval)
				# Publish only those that are directly matched by the newly
				# added match. If we end up with overlap, it is no biggie. It
				# is queued and rate-limited anyway.
				if ob is not None:
					for k, v in self._values.items():
						pt = PublishedTopic(k)
						if pt not in self._published and ob.match(pt.shorttopic):
							self._published.add(pt)
							self._publish(k, v)
		else:
			if self._subscriptions.subscribe_all(self._keep_alive_interval) is not None:
				self._publish_all()

	def _handle_write(self, topic, payload):
		logging.debug('[Write] Writing {} to {}'.format(payload, topic))
		value = json.loads(payload)['value']
		service, device_instance, path = self._get_uid_by_topic(topic)
		if service is None:
			raise Exception('Unknown service')

		self._set_dbus_value(service, '/' + path, value)

		# Run the queue as soon as possible
		GLib.idle_add(self._service_queue)

	def _handle_read(self, topic):
		logging.debug('[Read] Topic {}'.format(topic))
		service, device_instance, path = self._get_uid_by_topic(topic)
		if service is None:
			raise Exception('Unknown service')

		# Read a fresh value and make sure item is added. This is because a path
		# may not always send PropertiesChanged (eg vebus/Hub4/L1/AcPowerSetpoint)
		# but can nevertheless be read.
		value = self._get_dbus_value(service, '/' + path)
		if self._add_item(service, device_instance, path, value=value) == topic:
			self._client.publish(topic, json.dumps(dict(value=value)), retain=False)

	def _get_uid_by_topic(self, topic):
		action, system_id, service_type, device_instance, path = topic.split('/', 4)
		device_instance = int(device_instance)
		service = self._services.get('{}/{}'.format(service_type, device_instance))
		return service, device_instance, path

	def _dbus_name_owner_changed(self, name, oldowner, newowner):
		if not name.startswith('com.victronenergy.'):
			return
		if newowner != '':
			self._scan_dbus_service(name, publish=True)
			self._service_ids[newowner] = name
		elif oldowner != '':
			logging.info('[OwnerChange] Service disappeared: {}'.format(name))
			for path, topic in list(self._topics.items()):
				if path.startswith(name + '/'):
					# Leave the serial number alone
					if not topic.endswith('/system/0/Serial'):
						self._unpublish(topic)
					del self._topics[path]
					del self._values[topic]
			if name in self._services:
				del self._services[name]
			if oldowner in self._service_ids:
				del self._service_ids[oldowner]

	def _scan_dbus_service(self, service, publish=False):
		try:
			logging.info('[Scanning] service: {}'.format(service))
			try:
				device_instance = int(self._get_dbus_value(service, '/DeviceInstance'))
			except dbus.exceptions.DBusException as e:
				if e.get_dbus_name() == 'org.freedesktop.DBus.Error.UnknownObject' or \
					e.get_dbus_name() == 'org.freedesktop.DBus.Error.UnknownMethod':
					device_instance = 0
				else:
					raise
			except TypeError:
				device_instance = 0
			short_service_name = get_short_service_name(service, device_instance)
			self._services[short_service_name] = service
			try:
				items = self._get_dbus_value(service, '/')
			except dbus.exceptions.DBusException as e:
				if e.get_dbus_name() == 'org.freedesktop.DBus.Error.UnknownObject' or \
					e.get_dbus_name() == 'org.freedesktop.DBus.Error.UnknownMethod':
					self._introspect(service, device_instance, '/', publish)
					logging.warn('[Scanning] {} does not provide an item listing'.format(service))
					return
				else:
					raise

			if isinstance(items, dict):
				for path, value in items.items():
					topic = self._add_item(service, device_instance, path, value=value)
					if publish and topic is not None:
						self.publish(topic, value)

		except dbus.exceptions.DBusException as e:
			if e.get_dbus_name() == 'org.freedesktop.DBus.Error.ServiceUnknown' or \
				e.get_dbus_name() == 'org.freedesktop.DBus.Error.Disconnected':
				logging.info("[Scanning] Service disappeared while being scanned: %s", service)
			elif e.get_dbus_name() == 'org.freedesktop.DBus.Error.NoReply':
				logging.info("[Scanning] No response from service during scan: %s", service)
			else:
				raise

	def _introspect(self, service, device_instance, path, publish=True):
		value = self._dbus_conn.call_blocking(service, path, None, 'Introspect', '', [])
		tree = etree.fromstring(value)
		nodes = tree.findall('node')
		if len(nodes) == 0:
			for iface in tree.findall('interface'):
				if iface.attrib.get('name') == 'com.victronenergy.BusItem':
					v = self._get_dbus_value(service, path)
					topic = self._add_item(service, device_instance, path, value=v)
					if publish and topic is not None:
						self.publish(topic, v)
		else:
			for child in nodes:
				name = child.attrib.get('name')
				if name is not None:
					if path.endswith('/'):
						p = path + name
					else:
						p = path + '/' + name
					self._introspect(service, device_instance, p, publish=publish)

	def _on_dbus_items_changed(self, items, service_id=None):
		service = self._service_ids.get(service_id)
		if service is None:
			return

		if isinstance(items, dict):
			for path, changes in items.items():
				try:
					v = changes['Value']
				except KeyError:
					pass
				else:
					self._value_changed_inner(service, path, v)

	def _on_dbus_value_changed(self, changes, path=None, service_id=None):
		service = self._service_ids.get(service_id)
		if service is None:
			return

		value = changes.get("Value")
		if value is None:
			return

		self._value_changed_inner(service, path, value)

	def _value_changed_inner(self, service, path, value):
		uid = service + path
		topic = self._topics.get(uid)
		if topic is None:
			for service_short_name, service_name in self._services.items():
				if service_name == service:
					device_instance = service_short_name.split('/')[1]
					self._add_item(service, device_instance, path)
					logging.info('New item found: {}{}'.format(service_short_name, path))
					topic = self._topics[uid]
					break
			else:
				return
		self._values[topic] = value
		self.publish(topic, value)

	def _timer_service_queue(self):
		if len(self.queue) > 0 and time() - self._last_queue_run > 1.5:
			if self._service_queue():
				# The queue is not empty
				GLib.idle_add(self._service_queue)
		return True

	def _service_queue(self):
		# If we are not connected, we cannot service the queue
		if self._socket_watch is None:
			return False

		# To remain somewhat responsive, limit the number of items
		# published and schedule the rest when idle again.
		self._last_queue_run = time()
		for _ in range(50):
			try:
				topic, value = self.queue.popitem(last=False)
			except KeyError:
				return False
			else:
				try:
					self._client.publish(topic,
						None if value is None else json.dumps(dict(value=unwrap_dbus_value(value))),
						retain=True)
				except:
					logging.error('[Queue] Error publishing: {} {}'.format(topic, value))
					traceback.print_exc()

		return True

	def _add_item(self, service, device_instance, path, value=None):
		if not path.startswith('/'):
			path = '/' + path
		uid = service + path
		r = self._topics.get(uid)
		if r is not None:
			# Topic exist already
			return r

		service_type = get_service_type(service)
		if (service_type, path) in blocked_items:
			return None

		self._topics[uid] = topic = 'N/{}/{}/{}{}'.format(self._system_id, service_type, device_instance, path)
		self._values[topic] = value
		return topic

	def _get_dbus_value(self, service, path):
		return self._dbus_conn.call_blocking(service, path, None, 'GetValue', '', [])

	def _set_dbus_value(self, service, path, value):
		value = wrap_dbus_value(value)
		return self._dbus_conn.call_blocking(service, path, None, 'SetValue', 'v', [value])

def get_service_type(service_name):
	if not service_name.startswith(ServicePrefix):
		raise Exception('No victron service')
	return service_name.split('.')[2]


def get_service_base_name(service_name):
	if not service_name.startswith(ServicePrefix):
		raise Exception('No victron service')
	return '.'.join(service_name.split('.')[0:3])


def get_short_service_name(service, device_instance):
	return '{}/{}'.format(get_service_type(service), device_instance)


def dumpstacks(signal, frame):
	import threading
	id2name = dict((t.ident, t.name) for t in threading.enumerate())
	for tid, stack in sys._current_frames().items():
		logging.info ("=== {} ===".format(id2name[tid]))
		traceback.print_stack(f=stack)

def exit(mainloop, signal, frame):
	mainloop.quit()

def main():
	parser = argparse.ArgumentParser(description='Publishes values from the D-Bus to an MQTT broker')
	parser.add_argument('-d', '--debug', help='set logging level to debug', action='store_true')
	parser.add_argument('-q', '--mqtt-server', nargs='?', default=None, help='name of the mqtt server')
	parser.add_argument('-u', '--mqtt-user', default=None, help='mqtt user name')
	parser.add_argument('-P', '--mqtt-password', default=None, help='mqtt password')
	parser.add_argument('-c', '--mqtt-certificate', default=None, help='path to CA certificate used for SSL communication')
	parser.add_argument('-b', '--dbus', default=None, help='dbus address')
	parser.add_argument('-k', '--keep-alive', default=MAX_TOPIC_AGE, help='keep alive interval in seconds', type=int)
	parser.add_argument('-i', '--init-broker', action='store_true', help='Tries to setup communication with VRM MQTT broker')
	args = parser.parse_args()

	print("-------- dbus_mqtt, v{} is starting up --------".format(SoftwareVersion))
	logger = setup_logging(args.debug)

	mainloop = GLib.MainLoop()
	# Have a mainloop, so we can send/receive asynchronous calls to and from dbus
	DBusGMainLoop(set_as_default=True)
	keep_alive_interval = args.keep_alive if args.keep_alive > 0 else None
	handler = DbusMqtt(
		mqtt_server=args.mqtt_server, ca_cert=args.mqtt_certificate, user=args.mqtt_user,
		passwd=args.mqtt_password, dbus_address=args.dbus, keep_alive_interval=keep_alive_interval,
		init_broker=args.init_broker, debug=args.debug)

	# Quit the mainloop on ctrl+C
	signal.signal(signal.SIGINT, partial(exit, mainloop))

	# Handle SIGUSR1 and dump a stack trace
	signal.signal(signal.SIGUSR1, dumpstacks)

	# Start and run the mainloop
	try:
		mainloop.run()
	except KeyboardInterrupt:
		pass

if __name__ == '__main__':
	main()
