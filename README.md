dbus-mqtt
=========

A python script that publishes values from the D-Bus to an MQTT broker. The script also supports requests
from the MQTT broker to change values on the local D-Bus. This script only works with the D-Bus interface
defined for use with the Color Control GX (CCGX).

Set-up
------
Right now, there is no MQTT broker running on the CCGX itself. There is a package for mosquitto, which is a
popular MQTT broker. You can install it on the CCGX with:

	opkg install mosquitto

The broker is not started automatically. You have to start it yourself with the command:

	mosquitto -c /etc/mosquitto/mosquitto.conf

It is also possible to connect the a MQTT broker elsewhere using the command line options of the script.
For example:

	dbus-mqtt.py --mqtt-server my.mqqt.server

will connect to your favorite MQTT broker, assuming it allows access without authentication.

Notifications
-------------

When a value on the D-Bus changes, the script will send a message to the broker.
The MQTT topic looks like this:

	N/<portal ID>/<service_type>/<device instance>/<D-Bus path>

  * Portal ID is the VRM portal ID associated with the CCGX.
  * Service type is the part of the D-Bus service name that describes the service.
  * Device instance is a number used to make all services of the same type unique (this value is published
    on the D-Bus as /DeviceInstance)

The payload of the D-Bus value is wrapped in a dictionary and converted to json. The messages are retained by
the broker, so if you subscribe to the broker you'll always get last message for each subscribed topic.

Example:
Suppose we have a PV inverter, which reports a total AC power of 936W. The topic of the MQTT message would be:

	Topic: N/e0ff50a097c0/pvinverter/20/Ac/Power
	Payload: {"value": 936}

The value 20 in the topic is the device instance which may be different.

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

The device instance (in this case 257) of a service usually depends on the communication port used the
connect the device to the CCGX, so it is a good idea to check it before sending write requests. A nice way to
do this is by subscribing to the broker using wildcards.
For example:

	W/e0ff50a097c0/vebus/+/Hub4/L1/AcPowerSetpoint

will get you the list of all registered Multis/Quattros (=vebus services) which have publish
/Hub4/L1/AcPowerSetpoint D-Bus path. You can pick the device instance from the topics in the list.

Read requests
-------------

A read request will force the script to send a notification message of a specific D-Bus value. Again the
topic is identical to the notification message itself, except that the first character is a 'R'. Wildcards
in the topic are not supported. The payload will be ignored (it's best to keep it empty).

Example:
To retrieve the AC power of our favorite PV inverter we send:

	Topic: R/e0ff50a097c0/pvinverter/20/Ac/Power
	Payload: empty

The script will reply with this message (make sure you subscribe to it):

	Topic: N/e0ff50a097c0/pvinverter/20/Ac/Power
	Payload: {"value": 926}

Normally you do not need to use read requests, because most values are published automatically. There are
some exceptions however. Most important are the settings (com.victronenergy.settings on the D-Bus). If you
want to retrieve a setting you have to use a read request.

Connecting to the victron MQTT server
-------------------------------------

It is possible to forward all MQTT traffic from the CCGX to the victron MQTT server (mqtt.victronenergy.com).
If the script is started with the --init-broker option, it will register itself to the server. You can connect
to the MQTT server using you VRM username (email address) and password. All communication is encrypted
using SSL. Therefore you need the ca-certificate - ccgx-ca.crt - in this repository.

A convenient way to test this is using the mosquitto_sub tool, which is part of mosquitto (on debian linux
you need to install the mosquitto-clients package).

This command will get you the total system consumption:

	mosquitto_sub -v -t 'N/e0ff50a097c0/system/0/Ac/Consumption/Total/Power' -h mqtt.victronenergy.com -u <email> -P <passwd> --cafile ccgx-ca.crt -p 8883

If you have Full Control permissions on the VRM site, write requests will also be processed. For example:

	mosquitto_pub -t 'W/e0ff50a097c0/hub4/0/AcPowerSetpoint' -m '{"value":-100}' -h mqtt.victronenergy.com -u <email> -P <passwd> --cafile ccgx-ca.crt -p 8883
