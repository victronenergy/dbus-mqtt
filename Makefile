SRC_DIR = $(PWD)
SRC_VEDLIB_DIR = $(PWD)/ext/velib_python
INSTALL_CMD = install
DEST_LIB_DIR = $(bindir)/ext/velib_python

FILES = \
	$(SRC_DIR)/dbus_mqtt.py \
	$(SRC_DIR)/mqtt_gobject_bridge.py

VEDLIB_FILES = \
	$(SRC_VEDLIB_DIR)/logger.py \
	$(SRC_VEDLIB_DIR)/mosquitto_bridge_registrator.py \
	$(SRC_VEDLIB_DIR)/ve_utils.py \
	$(SRC_VEDLIB_DIR)/vedbus.py

help :
	@ echo "The following make targets are available"
	@ echo " help - print this message"
	@ echo " install - install everything"

clean: ;
distclean: ;

install_app : $(FILES)
	@if [ "$^" != "" ]; then \
		$(INSTALL_CMD) -d $(DESTDIR)$(bindir); \
		$(INSTALL_CMD) -t $(DESTDIR)$(bindir) $^; \
		echo installed $(DESTDIR)$(bindir)/$(notdir $^); \
	fi

install_velib_python: $(VEDLIB_FILES)
	@if [ "$^" != "" ]; then \
		$(INSTALL_CMD) -d $(DESTDIR)$(DEST_LIB_DIR); \
		$(INSTALL_CMD) -t $(DESTDIR)$(DEST_LIB_DIR) $^; \
		echo installed $(DESTDIR)$(DEST_LIB_DIR)/$(notdir $^); \
	fi

install: install_velib_python install_app

testinstall:
	$(eval TMP := $(shell mktemp -d))
	$(MAKE) DESTDIR=$(TMP) install
	(cd $(TMP) && ./dbus_mqtt.py --help > /dev/null)
	-rm -rf $(TMP)

.PHONY: help install_app install_velib_python install testinstall clean distclean
