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

The value 20 in the topic is the device instance which may be different on other systems.

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

This also is a convenient way to find out which device instances are used, which comes in handy when there are
multiple devices of the same type present.

*If you try this for the first time on your CCGX, you will probably not get any results. Please read the Keep-alive section below to find out why.*

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

Normally you do not need to use read requests, because most values are published automatically as they
change. For values that don't change often, most notably settings (com.victronenergy.settings on D-Bus),
you will have to use a read request to retrieve the current value.

Keep-alive
----------

In order to avoid a lot of traffic to our cloud server, the script contains a keep-alive mechanism. Default
keep-alive interval is 60 seconds. If the CCGX does not receive any read or write requests during that
interval, the notifications will be stopped, until the next read or write request is received. 
So to keep the notifications running, you'll have to send a read request regularly, for example:

	Topic: R/e0ff50a097c0/system/0/Serial
	Payload: empty

On a keep-alive timeout (at the end of the 60 second interval), all retained values will be removed from the
broker (by publishing an empty payload), so subscriptions will yield no result when the keep-alive is not 
active.
There is one exception: the CCGX serial number is always available. This is useful if you are communicating
with a CCGX on the local network: you can subscribe to the serial number, which is identical to the portal ID.

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

Note: because of [this security advisory](https://mosquitto.org/2017/05/security-advisory-cve-2017-7650/), the
client ID and username can't contain the `+`, `#` or `/` characters. `Mosquitto_pub` and `mosquitto_sub`
auto-generate the client ID with a `/` in it, so they need to be overridden. The `-I myclient_` takes care
of that.

This command will get you the total system consumption:

	mosquitto_sub -v -I myclient_ -c -t 'N/e0ff50a097c0/system/0/Ac/Consumption/Total/Power' -h mqtt.victronenergy.com -u <email> -P <passwd> --cafile venus-ca.crt -p 8883

You may need the full path to the cert file. On the CCGX it is in
`/etc/ssl/certs/ccgx-ca.pem`. You can also find the certificate in this repository as `venus-ca.crt`.

In case you do not receive the value you expect, please read the keep-alive section.

If you have Full Control permissions on the VRM site, write requests will also be processed. For example:

	mosquitto_pub -I myclient_ -t 'W/e0ff50a097c0/hub4/0/AcPowerSetpoint' -m '{"value":-100}' -h mqtt.victronenergy.com -u <email> -P <passwd> --cafile venus-ca.crt -p 8883

Again: do not set the retain flag when sending write requests.

Websockets
----------

The MQTT service on mqtt.victronenergy.com is also accessible through websockets, on webmqtt.victronenergy.com,
port 443. This allows for using MQTT from a web browser, supporting all aforementioned behavior. Note that
mqtt.victronenergy.com also has port 443 open, but this is not a websocket port.
