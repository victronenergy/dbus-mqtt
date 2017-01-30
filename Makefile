SRC_DIR = $(PWD)
SRC_PAHO_DIR = $(PWD)/paho
SRC_PAHO_MQTT_DIR = $(PWD)/paho/mqtt
SRC_VEDLIB_DIR = $(PWD)/ext/velib_python
INSTALL_CMD = install
DEST_LIB_DIR = $(bindir)/ext/velib_python
DEST_PAHO_DIR = $(bindir)/paho
DEST_PAHO_MQTT_DIR = $(bindir)/paho/mqtt

FILES = \
	$(SRC_DIR)/venus-ca.crt \
	$(SRC_DIR)/dbus_mqtt.py \
	$(SRC_DIR)/mqtt_gobject_bridge.py \
	$(SRC_DIR)/vrm_registrator.py \
	$(SRC_DIR)/mosquitto.conf

PAHO_FILES = \
	$(SRC_PAHO_DIR)/__init__.py

PAHO_MQTT_FILES = \
	$(SRC_PAHO_MQTT_DIR)/__init__.py \
	$(SRC_PAHO_MQTT_DIR)/client.py \
	$(SRC_PAHO_MQTT_DIR)/publish.py

VEDLIB_FILES = \
	$(SRC_VEDLIB_DIR)/logger.py \
	$(SRC_VEDLIB_DIR)/ve_utils.py \
	$(SRC_VEDLIB_DIR)/vedbus.py

help :
	@ echo "The following make targets are available"
	@ echo " help - print this message"
	@ echo " install - install everything"

clean: ;

install_app : $(FILES)
	@if [ "$^" != "" ]; then \
		$(INSTALL_CMD) -d $(DESTDIR)$(bindir); \
		$(INSTALL_CMD) -t $(DESTDIR)$(bindir) $^; \
		echo installed $(DESTDIR)$(bindir)/$(notdir $^); \
	fi

install_paho : $(PAHO_FILES)
	@if [ "$^" != "" ]; then \
		$(INSTALL_CMD) -d $(DESTDIR)$(DEST_PAHO_DIR); \
		$(INSTALL_CMD) -t $(DESTDIR)$(DEST_PAHO_DIR) $^; \
		echo installed $(DESTDIR)$(DEST_PAHO_DIR)/$(notdir $^); \
	fi

install_paho_mqtt : $(PAHO_MQTT_FILES)
	@if [ "$^" != "" ]; then \
		$(INSTALL_CMD) -d $(DESTDIR)$(DEST_PAHO_MQTT_DIR); \
		$(INSTALL_CMD) -t $(DESTDIR)$(DEST_PAHO_MQTT_DIR) $^; \
		echo installed $(DESTDIR)$(DEST_PAHO_MQTT_DIR)/$(notdir $^); \
	fi

install_velib_python: $(VEDLIB_FILES)
	@if [ "$^" != "" ]; then \
		$(INSTALL_CMD) -d $(DESTDIR)$(DEST_LIB_DIR); \
		$(INSTALL_CMD) -t $(DESTDIR)$(DEST_LIB_DIR) $^; \
		echo installed $(DESTDIR)$(DEST_LIB_DIR)/$(notdir $^); \
	fi

install: install_velib_python install_app install_paho install_paho_mqtt

.PHONY: help install_app install_velib_python install install_paho install_paho_mqtt
