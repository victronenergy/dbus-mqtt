#!/usr/bin/env python
import dbus
import json
import os
import sys
import time
import unittest


test_dir = os.path.dirname(__file__)
sys.path.insert(1, os.path.join(test_dir, '..'))
import dbus_mqtt
import paho.mqtt.client


TestHost = 'ernst-test'
TestPortalId = 'd0ff500097c0'


# @unittest.skip("Skip if no CCGX present")
class DbusMqttTest(unittest.TestCase):
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


class ConversionTest(unittest.TestCase):
	def test_dbus_wrap_double(self):
		value = 1.2
		dbus_value = dbus_mqtt.wrap_dbus_value(value)
		self.assertIsInstance(dbus_value, dbus.Double)
		self.assertEqual(dbus.Double(value, variant_level=1), dbus_value)

	def test_dbus_wrap_int(self):
		value = 1121
		dbus_value = dbus_mqtt.wrap_dbus_value(value)
		self.assertIsInstance(dbus_value, dbus.Int32)
		self.assertEqual(dbus.Int32(value, variant_level=1), dbus_value)

	def test_dbus_wrap_long_int(self):
		value = 1121232124727312535L
		dbus_value = dbus_mqtt.wrap_dbus_value(value)
		self.assertIsInstance(dbus_value, dbus.Int64)
		self.assertEqual(dbus.Int64(value, variant_level=1), dbus_value)

	def test_dbus_wrap_string(self):
		value = 'text'
		dbus_value = dbus_mqtt.wrap_dbus_value(value)
		self.assertIsInstance(dbus_value, dbus.String)
		self.assertEqual(dbus.String(value, variant_level=1), dbus_value)

	def test_dbus_wrap_array(self):
		value = [1]
		dbus_value = dbus_mqtt.wrap_dbus_value(value)
		self.assertIsInstance(dbus_value, dbus.Array)
		self.assertEqual(dbus.Array([dbus.Int32(1, variant_level=1)]), dbus_value)

	def test_dbus_wrap_dict(self):
		value = {'a' : 3, 'b': 7.0}
		dbus_value = dbus_mqtt.wrap_dbus_value(value)
		print(dbus_value)
		self.assertIsInstance(dbus_value, dbus.Dictionary)
		self.assertEqual(dbus.Dictionary({
			dbus.String('a', variant_level=1): dbus.Int32(3, variant_level=1),
			dbus.String('b', variant_level=1): dbus.Double(7.0, variant_level=1)}, variant_level=1),
			dbus_value)

	def test_dbus_unwrap_double(self):
		dbus_value = dbus.Double(1.23, variant_level=1)
		value = dbus_mqtt.unwrap_dbus_value(dbus_value)
		self.assertIsInstance(value, float)
		self.assertEqual(float(dbus_value), value)

	def test_dbus_unwrap_byte(self):
		dbus_value = dbus.Byte(245, variant_level=1)
		value = dbus_mqtt.unwrap_dbus_value(dbus_value)
		self.assertIsInstance(value, int)
		self.assertEqual(int(dbus_value), value)

	def test_dbus_unwrap_int16(self):
		dbus_value = dbus.Int16(12, variant_level=1)
		value = dbus_mqtt.unwrap_dbus_value(dbus_value)
		self.assertIsInstance(value, int)
		self.assertEqual(int(dbus_value), value)

	def test_dbus_unwrap_int32(self):
		dbus_value = dbus.Int32(123, variant_level=1)
		value = dbus_mqtt.unwrap_dbus_value(dbus_value)
		self.assertIsInstance(value, int)
		self.assertEqual(int(dbus_value), value)

	def test_dbus_unwrap_int32(self):
		dbus_value = dbus.Int32(3323213, variant_level=1)
		value = dbus_mqtt.unwrap_dbus_value(dbus_value)
		self.assertIsInstance(value, int)
		self.assertEqual(int(dbus_value), value)

	def test_dbus_unwrap_int64(self):
		dbus_value = dbus.Int64(3323213, variant_level=1)
		value = dbus_mqtt.unwrap_dbus_value(dbus_value)
		self.assertIsInstance(value, int)
		self.assertEqual(int(dbus_value), value)

	def test_dbus_unwrap_int64_large(self):
		dbus_value = dbus.Int64(33232133232323L, variant_level=1)
		value = dbus_mqtt.unwrap_dbus_value(dbus_value)
		self.assertIsInstance(value, int)
		self.assertEqual(int(dbus_value), value)

	def test_dbus_unwrap_string(self):
		dbus_value = dbus.String('abcd', variant_level=1)
		value = dbus_mqtt.unwrap_dbus_value(dbus_value)
		self.assertIsInstance(value, unicode)
		self.assertEqual(str(dbus_value), value)

	def test_dbus_unwrap_array(self):
		dbus_value = dbus.Array([dbus.Int32(3, variant_level=1), dbus.Int32(7, variant_level=1)],
			variant_level=1)
		value = dbus_mqtt.unwrap_dbus_value(dbus_value)
		self.assertIsInstance(value, list)
		self.assertEqual([3, 7], value)

	def test_dbus_unwrap_empty_array(self):
		dbus_value = dbus.Array([], variant_level=1)
		value = dbus_mqtt.unwrap_dbus_value(dbus_value)
		self.assertIsNone(value)

	def test_dbus_unwrap_dict(self):
		dbus_value = dbus.Dictionary({
			dbus.String('a', variant_level=1): dbus.Double(3.2, variant_level=1),
			dbus.String('b', variant_level=1): dbus.Double(3.7, variant_level=1)},
			variant_level=1)
		value = dbus_mqtt.unwrap_dbus_value(dbus_value)
		self.assertIsInstance(value, dict)
		self.assertEqual({'a':3.2, 'b':3.7}, value)

if __name__ == '__main__':
	unittest.main()
