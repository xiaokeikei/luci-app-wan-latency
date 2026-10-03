# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2026 xiaokeikei

include $(TOPDIR)/rules.mk

LUCI_TITLE:=WAN latency monitor for LuCI
LUCI_DESCRIPTION:=Continuously measures WAN latency, stores compact time-series data, and shows an interactive LuCI dashboard with custom targets and time ranges.
LUCI_DEPENDS:=+luci-base +lua +luci-lib-nixio +cgi-io +rpcd-mod-file +curl +ip-full
LUCI_PKGARCH:=all
LUCI_MAINTAINER:=xiaokeikei
LUCI_URL:=https://github.com/xiaokeikei/luci-app-wan-latency
PKG_VERSION:=1.4.0
PKG_RELEASE:=1
PKG_LICENSE:=GPL-2.0-only
PKG_LICENSE_FILES:=LICENSE

define Package/luci-app-wan-latency/conffiles
/etc/config/wan-latency
endef

define Package/luci-app-wan-latency/postinst
#!/bin/sh
[ -n "$${IPKG_INSTROOT}" ] || {
	/etc/init.d/wan-latency enable
	/etc/init.d/wan-latency restart
	rm -f /www/cgi-bin/wan-latency
	rm -f /tmp/luci-indexcache.* 2>/dev/null
	rm -rf /tmp/luci-modulecache/
	/etc/init.d/rpcd reload 2>/dev/null
	/etc/init.d/uhttpd reload 2>/dev/null
}
exit 0
endef

define Package/luci-app-wan-latency/prerm
#!/bin/sh
[ -n "$${IPKG_INSTROOT}" ] || /etc/init.d/wan-latency stop
exit 0
endef

include $(TOPDIR)/feeds/luci/luci.mk

# call BuildPackage - OpenWrt buildroot signature
