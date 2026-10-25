#!/bin/sh
# Remove desktop-switcher. Usage: sudo ./uninstall.sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "Please run with sudo: sudo $0" >&2
    exit 1
fi

rm -rf /usr/lib/desktop-switcher
rm -f /usr/bin/desktop-switcher \
      /etc/systemd/system/desktop-switcher-secondary@.service \
      /etc/polkit-1/rules.d/50-desktop-switcher.rules \
      /usr/share/applications/desktop-switcher.desktop \
      /etc/desktop-switcher.conf
systemctl daemon-reload
echo "Removed. Your pair setting in ~/.config/desktop-switcher is left in place."
