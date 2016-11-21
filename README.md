dbus-mqtt
=========

A python script that publishes values from the D-Bus to an MQTT broker. The script also supports requests
from the MQTT broker to change values on the local D-Bus. This script only works with the D-Bus interface
defined for use with the Color Control GX (CCGX).

By default, dbus-mqtt will connect to a Mosquitto MQTT broker running on the CCGX itself. The broker is
accessible on the local network at TCP port 1883. Furthermore the broker is configured to forward all
communication to the central Victron MQTT broker (mqtt.victronenergy.com), which allows you to monitor and
control your CCGX over the internet. You'll need your VRM credentials to access this broker. See 'Connecting
to the Victron MQTT server' below.

Set-up
------
Starting from CCGX version 1.70, dbus-mqtt is installed by default, but is not enabled. You can enable it in
Settings->Services.

Notifications
-------------

When a value on the D-Bus changes, the script will send a message to the broker.
The MQTT topic looks like this:

	N/<portal ID>/<service_type>/<device instance>/<D-Bus path>

  * Portal ID is the VRM portal ID associated with the CCGX. You can find the portal ID on the CCGX in
    Settings->VRM online portal->VRM Portal ID. On the VRM portal itself, you can find the ID in Settings
    tab.
  * Service type is the part of the D-Bus service name that describes the service.
  * Device instance is a number used to make all services of the same type unique (this value is published
    on the D-Bus as /DeviceInstance).

The payload of the D-Bus value is wrapped in a dictionary and converted to json. The messages are retained by
the broker, so if you subscribe to the broker you'll always get the last message for each subscribed topic.

Example:
Suppose we have a PV inverter, which reports a total AC power of 936W. The topic of the MQTT message would be:

	Topic: N/e0ff50a097c0/pvinverter/20/Ac/Power
	Payload: {"value": 936}

The value 20 in the topic is the device instance which may be different.

There are 2 special cases.
  * A D-Bus value may be invalid. This happens with values that are not always present. For example: a single
    phase PV inverter will not provide a power value on phase 2. So /Ac/L2/Power is invalid. In that case the
    payload of the MQTT message will be {"value": null}.
  * A device may disappear from the D-Bus. For example: most PV inverters shut down at night, causing a
    communication breakdown. If this happens a notification will be sent for all topics related to the device.
    The payload will be empty (zero bytes, so no valid JSON). This will force the broker to remove the items
    from the list of retained topics.

If you want a roundup of all devices connected to the CCGX subscribe to this topic:

	N/e0ff50a097c0/+/+/ProductId

This also is a convenient way to find out which device instances are used, which comes in hany when there are
multiple devices of the same type present.

Write requests
--------------

Write requests can be sent to change values on the D-Bus. The format looks like the notification. Instead of
a N, the topic should start with a W. The payload format is identical.

Example:
On a Hub-4 system we can change the AC-In setpoint with this message:

	Topic: W/e0ff50a097c0/vebus/257/Hub4/L1/AcPowerSetpoint
	Payload: {"value": -200}

Important: do not set the retain flag in write requests, because that would cause the request to be repeated
each time the MQTT-service connects to the broker.

The device instance (in this case 257) of a service usually depends on the communication port used the
connect the device to the CCGX, so it is a good idea to check it before sending write requests. A nice way to
do this is by subscribing to the broker using wildcards.
For example:

	N/e0ff50a097c0/vebus/+/Hub4/L1/AcPowerSetpoint

will get you the list of all registered Multis/Quattros (=vebus services) which have published
/Hub4/L1/AcPowerSetpoint D-Bus path. You can pick the device instance from the topics in the list.

Read requests
-------------

A read request will force the script to send a notification message of a specific D-Bus value. Again the
topic is identical to the notification message itself, except that the first character is a 'R'. Wildcards
in the topic are not supported. The payload will be ignored (it's best to keep it empty).

Example:
To retrieve the AC power of our favorite PV inverter we publish:

	Topic: R/e0ff50a097c0/pvinverter/20/Ac/Power
	Payload: empty

The script will reply with this message (make sure you subscribe to it):

	Topic: N/e0ff50a097c0/pvinverter/20/Ac/Power
	Payload: {"value": 926}

Normally you do not need to use read requests, because most values are published automatically. There are
some exceptions however. Most important are the settings (com.victronenergy.settings on the D-Bus). If you
want to retrieve a setting you have to use a read request.

Keep alive
----------

In order to avoid a lot of traffic to our cloud server, the script contains a keep-alive mechanism. Default
keep-alive interval is 60 seconds. If the system does not receive any read or write requests during that
interval, the notifications will be stopped, until the next read or write request is received.
So to keep the notifications running, you'll have to send a read request regularly, for example:

	Topic: R/e0ff50a097c0/system/0/Serial
	Payload: empty

Connecting to the Victron MQTT server
-------------------------------------

If the MQTT service is enabled, the CCGX will forward all notifications from the CCGX to the Victron MQTT
server (mqtt.victronenergy.com). All communication is encrypted using SSL. You can connect to the MQTT
server using your VRM credentials and subscribe to the notifications sent by your CCGX. It is also possible
to send read and write requests to the CCGX. You can only receive notifications from systems in your own VRM
site list, and to send write requests you need the 'Full Control' permission. This is the default is you have
registered the system yourself. The 'Monitor Only' permission allows subscription to notifications only
(read only access).

A convenient way to test this is using the mosquitto_sub tool, which is part of Mosquitto (on debian linux
you need to install the mosquitto-clients package).

This command will get you the total system consumption:

	mosquitto_sub -v -t 'N/e0ff50a097c0/system/0/Ac/Consumption/Total/Power' -h mqtt.victronenergy.com -u <email> -P <passwd> --cafile venus-ca.crt -p 8883

If you have Full Control permissions on the VRM site, write requests will also be processed. For example:

	mosquitto_pub -t 'W/e0ff50a097c0/hub4/0/AcPowerSetpoint' -m '{"value":-100}' -h mqtt.victronenergy.com -u <email> -P <passwd> --cafile venus-ca.crt -p 8883

Again: do not set the retain flag when sending write requests.

Websockets
----------

The MQTT service on mqtt.victronenergy.com is also accessible through websockets, on port 443. 
This allows for using MQTT from a web browser, supporting all aforementioned behavior.

Should you run into HTTP 400 errors, this is because the client needs to support the base64 or binary 
protocol. Read [this](http://stackoverflow.com/questions/15962359) for more information.
