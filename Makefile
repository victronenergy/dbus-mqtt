SOURCEDIR = $(PWD)
SRC_PAHODIR = $(PWD)/paho
SRC_PAHO_MQTT_DIR = $(PWD)/paho/mqtt
VEDLIBDIR = $(PWD)/ext/velib_python
INSTALL_CMD = install
LIBDIR = $(bindir)/ext/velib_python
PAHODIR = $(bindir)/paho
PAHO_MQTT_DIR = $(bindir)/paho/mqtt

FILES = \
	$(SOURCEDIR)/dbus-mqtt.py

PAHO_FILES = \
	$(SRC_PAHODIR)/__init__.py

PAHO_MQTT_FILES = \
	$(SRC_PAHO_MQTT_DIR)/__init__.py \
	$(SRC_PAHO_MQTT_DIR)/client.py \
	$(SRC_PAHO_MQTT_DIR)/publish.py

VEDLIB_FILES = \
	$(VEDLIBDIR)/logger.py \
	$(VEDLIBDIR)/ve_utils.py \
	$(VEDLIBDIR)/vedbus.py

help :
	@ echo "The following make targets are available"
	@ echo " help - print this message"
	@ echo " install - install everything"

install_app : $(FILES)
	@if [ "$^" != "" ]; then \
		$(INSTALL_CMD) -d $(DESTDIR)$(bindir); \
		$(INSTALL_CMD) -t $(DESTDIR)$(bindir) $^; \
		echo installed $(DESTDIR)$(bindir)/$(notdir $^); \
	fi

install_paho : $(PAHO_FILES)
	@if [ "$^" != "" ]; then \
		$(INSTALL_CMD) -d $(DESTDIR)$(PAHODIR); \
		$(INSTALL_CMD) -t $(DESTDIR)$(PAHODIR) $^; \
		echo installed $(DESTDIR)$(PAHODIR)/$(notdir $^); \
	fi

install_paho_mqtt : $(PAHO_MQTT_FILES)
	@if [ "$^" != "" ]; then \
		$(INSTALL_CMD) -d $(DESTDIR)$(PAHO_MQTT_DIR); \
		$(INSTALL_CMD) -t $(DESTDIR)$(PAHO_MQTT_DIR) $^; \
		echo installed $(DESTDIR)$(PAHO_MQTT_DIR)/$(notdir $^); \
	fi

install_velib_python: $(VEDLIB_FILES)
	@if [ "$^" != "" ]; then \
		$(INSTALL_CMD) -d $(DESTDIR)$(LIBDIR); \
		$(INSTALL_CMD) -t $(DESTDIR)$(LIBDIR) $^; \
		echo installed $(DESTDIR)$(LIBDIR)/$(notdir $^); \
	fi

install: install_velib_python install_app install_paho install_paho_mqtt

.PHONY: help install_app install_velib_python install install_paho install_paho_mqtt
