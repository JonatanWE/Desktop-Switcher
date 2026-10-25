# Desktop Switcher

Switch between two Linux desktops (for example KDE Plasma and Hyprland) with one key, without logging out, rebooting or closing anything.

**Status: phase 1, untested on real hardware.** Both desktops run at the same time under your own user, and the switch flips which one is on screen. Windows stay on the desktop where you opened them. Carrying apps across desktops (Chrome tabs, unsaved editor work) is phase 2.

## How it works

1. You log in to one desktop of your pair from the normal login screen. This is the *primary* desktop.
2. The first time you press switch, the other desktop starts in the background on its own virtual terminal (VT 8 by default). The screen only switches once it has stayed up for two seconds; if it fails to start, you stay where you are and get an error.
3. Every later press just flips between the two. Both keep running, so nothing closes.

The second desktop runs as a systemd service that opens a real login session on its terminal, so it gets the GPU and input exactly like a normal login. It also gets its own D-Bus session bus, so two desktops under one user do not fight over the same services.

## Install (CachyOS / Arch)

```sh
git clone https://github.com/JonatanWE/desktop-switcher
cd desktop-switcher
sudo ./install.sh            # or: sudo ./install.sh --vt 9
```

This installs:

| File | Purpose |
| --- | --- |
| `/usr/bin/desktop-switcher` | the command |
| `/usr/lib/desktop-switcher/` | its Python code (standard library only) |
| `/etc/systemd/system/desktop-switcher-secondary@.service` | runs the background desktop |
| `/etc/polkit-1/rules.d/50-desktop-switcher.rules` | lets you start/stop *your own* background desktop without a password |
| `/usr/share/applications/desktop-switcher.desktop` | a "Switch Desktop" launcher entry |
| `/etc/desktop-switcher.conf` | which VT the background desktop uses |

Remove everything with `sudo ./uninstall.sh`.

## Set up your pair

```sh
desktop-switcher list                  # desktops your login screen offers
desktop-switcher pair hyprland plasma  # use the ids from the list
desktop-switcher doctor                # checks setup, including NVIDIA settings
```

## Bind a key

Bind `desktop-switcher switch` to the same key in **both** desktops.

- **KDE Plasma:** System Settings, Keyboard, Shortcuts, Add New, Command or Script. Command: `desktop-switcher switch`.
- **Hyprland:** in `~/.config/hypr/hyprland.conf`: `bind = SUPER, F12, exec, desktop-switcher switch`
- **Sway:** in `~/.config/sway/config`: `bindsym Mod4+F12 exec desktop-switcher switch`
- **niri:** in `~/.config/niri/config.kdl`, inside `binds`: `Mod+F12 { spawn "desktop-switcher" "switch"; }`
- **GNOME:** Settings, Keyboard, Custom Shortcuts, command `desktop-switcher switch`.

You can also start "Switch Desktop" from the app launcher.

## Commands

| Command | What it does |
| --- | --- |
| `desktop-switcher switch` | go to the other desktop, starting it if needed |
| `desktop-switcher switch --dry-run` | print what switch would do |
| `desktop-switcher status` | show which desktops are running and on which VT |
| `desktop-switcher stop` | stop the background desktop (closes apps open in it) |
| `desktop-switcher doctor` | check the installation |

## Known limits in phase 1

- **Windows do not move.** Each window stays on the desktop where it was opened.
- **Single-instance apps.** Chrome, Discord and Steam allow only one copy per user. If Chrome is open on desktop A and you launch it on desktop B, the new window will appear on desktop A. Start such apps on the desktop where you want them, or close them first. Phase 2 fixes this.
- **Which desktop runs in the background.** KDE Plasma and GNOME depend on the systemd user session shared by your whole account, so they must be the desktop you log in to. The background desktop must be a standalone compositor such as niri, Hyprland or Sway. niri is started directly with `niri` instead of `niri-session`, because `niri-session` would log you out of the other desktop when it stops. `desktop-switcher doctor` shows which of your pair can run in the background.
- **Wayland only.** X11 sessions are listed but cannot be paired yet.
- **NVIDIA:** `nvidia_drm.modeset=1` is required. `NVreg_PreserveVideoMemoryAllocations=1` is recommended so windows are not corrupted after a switch. `doctor` checks both.

## Troubleshooting

- If the switch hangs or the screen stays black, press **Ctrl+Alt+F1** to F7 to get back to your login desktop. The background desktop is on **Ctrl+Alt+F8** by default.
- Logs of the background desktop: `journalctl -b -u desktop-switcher-secondary@$USER`
- Start over: `desktop-switcher stop`, then `desktop-switcher switch`.

## Development

```sh
python -m unittest discover -s tests -v
python -m desktop_switcher --help
```

## Roadmap

1. **Phase 1 (this):** both desktops running, one-key switch.
2. **Phase 2:** a background app layer (wprs) so chosen apps follow you between desktops with tabs and unsaved work intact.
3. **Phase 3:** a settings app where you pick your two desktops and choose per app whether it runs in the background layer or on one desktop only, plus a tray button and an AUR package.
