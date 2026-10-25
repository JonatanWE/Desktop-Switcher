#!/bin/sh
# Install desktop-switcher system-wide. Usage: sudo ./install.sh [--vt N]
set -eu

VT=8
while [ $# -gt 0 ]; do
    case "$1" in
        --vt) VT="$2"; shift 2 ;;
        -h|--help) echo "Usage: sudo $0 [--vt N]   (virtual terminal for the background desktop, default 8)"; exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done

case "$VT" in
    ''|*[!0-9]*) echo "--vt must be a number" >&2; exit 2 ;;
esac
if [ "$VT" -lt 2 ] || [ "$VT" -gt 63 ]; then
    echo "--vt must be between 2 and 63" >&2; exit 2
fi

if [ "$(id -u)" -ne 0 ]; then
    echo "Please run with sudo: sudo $0" >&2
    exit 1
fi

SRC=$(cd "$(dirname "$0")" && pwd)

rm -rf /usr/lib/desktop-switcher
install -d /usr/lib/desktop-switcher/desktop_switcher
install -m644 "$SRC"/desktop_switcher/*.py /usr/lib/desktop-switcher/desktop_switcher/
install -m755 "$SRC/data/desktop-switcher" /usr/bin/desktop-switcher

sed "s/@VT@/$VT/g" "$SRC/data/desktop-switcher-secondary@.service" \
    > /etc/systemd/system/desktop-switcher-secondary@.service
chmod 644 /etc/systemd/system/desktop-switcher-secondary@.service

install -d /etc/polkit-1/rules.d
install -m644 "$SRC/data/50-desktop-switcher.rules" /etc/polkit-1/rules.d/50-desktop-switcher.rules
install -m644 "$SRC/data/desktop-switcher.desktop" /usr/share/applications/desktop-switcher.desktop
printf '[secondary]\nvt = %s\n' "$VT" > /etc/desktop-switcher.conf

systemctl daemon-reload

echo "Installed. Background desktop uses VT $VT."
echo "Next, as your normal user:"
echo "  desktop-switcher list"
echo "  desktop-switcher pair <desktop-a> <desktop-b>"
echo "  desktop-switcher doctor"
