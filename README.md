# Desktop Switcher
# This project is vibe coded, i don't know how to code.

Switch between two Linux desktops with one key, without logging out, rebooting or closing anything.

Both desktops keep running side by side, so every app you left open is still there when you come back. Tested on CachyOS with an NVIDIA RTX 4070, using KDE Plasma and niri. please tell me if it worked on your system so i can update this list, and if you have problems feel free to contact me or fix them and send me your resault.

## Quick start

1. **Download and install** (in a terminal):
   ```sh
   git clone https://github.com/JonatanWE/desktop-switcher
   cd desktop-switcher
   sudo ./install.sh
   ```
2. **Choose your two desktops.** `list` shows the names your login screen uses:
   ```sh
   desktop-switcher list
   desktop-switcher pair plasma niri
   ```
3. **Check the setup:**
   ```sh
   desktop-switcher doctor
   ```
4. **Add the shortcut.** This binds **Super+S** in niri and Plasma for you:
   ```sh
   desktop-switcher shortcut
   ```
   Log out of Plasma and back in once so its shortcut takes effect.
5. **Let your browser, Discord and Steam follow you** (optional, see [Apps that only run once](#apps-that-only-run-once)):
   ```sh
   desktop-switcher apps setup
   ```
6. **Press Super+S.** The first time, the other desktop starts in the background, which takes a few seconds. After that, switching is instant.

## Which desktops work

- **The desktop you log in to** can be any desktop, including KDE Plasma and GNOME.
- **The background desktop** must be a standalone compositor, such as **niri**, **Hyprland** or **Sway**. KDE Plasma and GNOME can't run in the background, because they share parts of your account's session with the desktop you logged in to.

`desktop-switcher doctor` tells you which of your two desktops can run in the background.

## Everyday use

| Command | What it does |
| --- | --- |
| Super+S, or `desktop-switcher switch` | switch to the other desktop |
| `desktop-switcher status` | show which desktops are running |
| `desktop-switcher stop` | close the background desktop and everything open in it |
| `desktop-switcher doctor` | check the setup |
| `desktop-switcher shortcut` | add Super+S to niri and Plasma |
| `desktop-switcher apps` | show where your browser, Discord and Steam are running |

Good to know:

- **Windows stay on their own desktop.** An app opened in niri stays in niri.
- **For other desktops** than niri and Plasma, bind a key to the command `desktop-switcher switch` in that desktop's keyboard settings.

## Apps that only run once

Browsers, Discord and Steam run only once per user. Normally, if one is open on one desktop and you start it on the other, its window opens on the first desktop, where you can't see it.

After `desktop-switcher apps setup`, opening one of these apps from your app menu or launcher moves it to the desktop you are on:

- **Chrome** (also Chromium and Brave) closes on the other desktop and opens here with all your tabs.
- **Firefox** closes on the other desktop and opens here. To get your tabs back, turn on **Open previous windows and tabs** in Firefox's settings (General, Startup) once.
- **Discord** closes on the other desktop and opens here.
- **Steam** shuts down on the other desktop and opens here. This can take up to a minute; a notification tells you it's moving. Close your game first.

Text you typed but didn't send or save inside the app, such as a half-written Discord message or form, can be lost when it moves.

The setup adds your own copies of these apps' launchers to `~/.local/share/applications`, so it works the same in both desktops and survives app updates. Apps that start on their own when you log in, and apps installed as Flatpak, are not moved. To go back to the normal launchers, run `desktop-switcher apps remove`.

You can also move an app from a terminal or a keyboard shortcut with `desktop-switcher open chrome` (or `firefox`, `discord`, `steam`, `chromium`, `brave`).

## If something goes wrong

- **The switch fails.** You stay on your current desktop and get an error message. See what happened with:
  ```sh
  journalctl -b -u desktop-switcher-secondary@$USER
  ```
- **The screen is black or stuck.** Ctrl+Alt+F1 to F7 takes you back to the desktop you logged in to. The background desktop is on Ctrl+Alt+F8.
- **Start over:** `desktop-switcher stop`, then press Super+S again.
- **NVIDIA graphics:** if windows look glitchy after switching, and `doctor` warns about video memory, add `options nvidia NVreg_PreserveVideoMemoryAllocations=1` to a file in `/etc/modprobe.d/` and reboot.

## Update or remove

- **Update:** `git pull` in the `desktop-switcher` folder, then `sudo ./install.sh` again.
- **Remove:** `desktop-switcher apps remove`, then `sudo ./uninstall.sh`. Your settings in `~/.config/desktop-switcher` are kept.

## How it works

You log in to one desktop as usual. The other desktop runs as a system service that opens its own login session on virtual terminal 8, so it gets the graphics card and keyboard exactly like a normal login. It also gets its own D-Bus bus, so the two desktops don't fight over the same services. Switching just changes which login session is on screen.

The installer adds these files:

| File | Purpose |
| --- | --- |
| `/usr/bin/desktop-switcher` | the command |
| `/usr/lib/desktop-switcher/` | its Python code (standard library only) |
| `/etc/systemd/system/desktop-switcher-secondary@.service` | runs the background desktop |
| `/etc/polkit-1/rules.d/50-desktop-switcher.rules` | lets you start and stop your own background desktop without a password |
| `/usr/share/applications/desktop-switcher.desktop` | a "Switch Desktop" entry in the app menu |
| `/etc/desktop-switcher.conf` | which virtual terminal the background desktop uses |

To use another terminal than 8, install with `sudo ./install.sh --vt 9`.

## Development

```sh
python -m unittest discover -s tests -v
python -m desktop_switcher --help
```
