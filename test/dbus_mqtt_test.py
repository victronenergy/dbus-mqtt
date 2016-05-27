#!/usr/bin/env python
import json
import os
import sys
import time
import unittest


test_dir = os.path.dirname(__file__)
sys.path.insert(1, os.path.join(test_dir, '..'))
import paho.mqtt.client


TestHost = 'ernst-test'
TestPortalId = 'd0ff500097c0'


class DbusMqttTest(unittest.TestCase):
	def __init__(self, methodName='runTest'):
		unittest.TestCase.__init__(self, methodName)

	def test_notifications(self):
		client = paho.mqtt.client.Client()
		notifications = []
		client.on_connect = lambda c,d,f,r: c.subscribe('N/#', 0)
		client.connect(TestHost)
		client.loop_start()
		time.sleep(2) # wait for retained messages
		client.on_message = lambda c,d,msg: notifications.append(msg)
		time.sleep(2)
		client.loop_stop(True)
		self.assertTrue(len(notifications) > 0)
		for n in notifications:
			action, system_id, service_type, device_instance, path = n.topic.split('/', 4)
			self.assertEqual(action, 'N')
			self.assertEqual(system_id, TestPortalId)
			# If the statements below raise an exception, the test will fail
			di = int(device_instance)
			v = json.loads(n.payload)['value']

	def test_request(self):
		client = paho.mqtt.client.Client()
		notifications = []
		client.on_connect = lambda c,d,f,r: c.subscribe('N/#', 0)
		client.connect(TestHost)
		client.loop_start()
		time.sleep(2) # wait for retained messages
		client.on_message = lambda c,d,msg: notifications.append(msg)
		topic = 'R/{}/settings/0/Settings/Vrmlogger/LogInterval'.format(TestPortalId)
		client.publish(topic, '')
		time.sleep(1)
		client.loop_stop(True)
		self.assertTrue(len(notifications) > 0)
		topic = 'N' + topic[1:]
		for n in notifications:
			if n.topic == topic:
				v = int(json.loads(n.payload)['value'])
				break
		else:
			raise Exception('Topic not found')

	def _write_topic(self, topic, value):
		client = paho.mqtt.client.Client()
		notifications = []
		client.on_connect = lambda c,d,f,r: c.subscribe('N/#', 0)
		client.connect(TestHost)
		client.loop_start()
		client.on_message = lambda c,d,msg: notifications.append(msg)
		client.publish(topic, json.dumps({'value': value}))
		time.sleep(1)
		client.loop_stop(True)
		self.assertTrue(len(notifications) > 0)
		topic = 'N' + topic[1:]
		v = None
		for n in notifications:
			if n.topic == topic:
				v = int(json.loads(n.payload)['value'])
		self.assertEqual(v, value)

	def test_write(self):
		# @todo EV Bad test: success depends on current value on D-Bus
		self._write_topic('W/{}/system/0/Relay/0/State'.format(TestPortalId), 0)
		self._write_topic('W/{}/system/0/Relay/0/State'.format(TestPortalId), 1)

	def test_write_unknown_path(self):
		# @todo EV Bad test: success depends on current value on D-Bus
		self._write_topic('W/{}/settings/0/Settings/Vrmlogger/Logmode'.format(TestPortalId), 0)
		self._write_topic('W/{}/settings/0/Settings/Vrmlogger/Logmode'.format(TestPortalId), 1)


if __name__ == '__main__':
	unittest.main()
