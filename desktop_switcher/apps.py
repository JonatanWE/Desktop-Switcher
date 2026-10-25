"""Move apps that only run once per user to the desktop you open them on.

Browsers, Discord and Steam allow one running copy per user. Started a second
time, they hand the request to the running copy, so the window opens on
whichever desktop that copy lives on. ``desktop-switcher open`` closes the
copy on the other desktop first, then starts the app here.

A process belongs to the desktop whose Wayland (or X11) display is in its
environment. Both desktops share one runtime directory, so each gets its own
display name, such as wayland-0 and wayland-1.
"""

from __future__ import annotations

import configparser
import os
import re
import shlex
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

MARKER = "X-Desktop-Switcher"


@dataclass(frozen=True)
class App:
    id: str
    name: str
    exe_names: frozenset[str]  # basenames of the main binary in /proc/PID/exe
    command: tuple[str, ...]  # how to start it when no command is given
    desktop_file: str
    quit_command: tuple[str, ...] = ()  # graceful quit; empty means SIGTERM
    restore_args: tuple[str, ...] = ()  # added when it was moved here
    quit_timeout: float = 15.0


APPS = {
    app.id: app
    for app in (
        App(
            "chrome",
            "Google Chrome",
            frozenset({"chrome"}),
            ("google-chrome-stable",),
            "google-chrome.desktop",
            restore_args=("--restore-last-session",),
        ),
        App(
            "chromium",
            "Chromium",
            frozenset({"chromium"}),
            ("chromium",),
            "chromium.desktop",
            restore_args=("--restore-last-session",),
        ),
        App(
            "brave",
            "Brave",
            frozenset({"brave"}),
            ("brave",),
            "brave-browser.desktop",
            restore_args=("--restore-last-session",),
        ),
        # Firefox has no flag to restore tabs; it reopens them when "Open
        # previous windows and tabs" is on in its settings.
        App("firefox", "Firefox", frozenset({"firefox", "firefox-bin"}), ("firefox",), "firefox.desktop"),
        App("discord", "Discord", frozenset({"Discord"}), ("discord",), "discord.desktop"),
        App(
            "steam",
            "Steam",
            frozenset({"steam"}),
            ("steam",),
            "steam.desktop",
            quit_command=("steam", "-shutdown"),
            quit_timeout=60.0,
        ),
    )
}


# Apps the user added ----------------------------------------------------


class AddError(Exception):
    pass


def custom_apps_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "desktop-switcher" / "apps.ini"


def _read_custom() -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(custom_apps_path())
    return parser


def _write_custom(parser: configparser.ConfigParser) -> None:
    path = custom_apps_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        parser.write(fh)


def custom_apps() -> dict[str, App]:
    found = {}
    parser = _read_custom()
    for app_id in parser.sections():
        section = parser[app_id]
        try:
            found[app_id] = App(
                app_id,
                section.get("name", app_id),
                frozenset(n.strip() for n in section["process"].split(",") if n.strip()),
                tuple(shlex.split(section["command"])),
                section["launcher"],
                quit_command=tuple(shlex.split(section.get("quit", ""))),
            )
        except (KeyError, ValueError):
            continue  # a broken entry; leave it for the user to fix
    return found


def all_apps() -> dict[str, App]:
    return {**custom_apps(), **APPS}


def _launcher_command(text: str) -> tuple[str, list[str]]:
    """Name and first Exec command of a .desktop file, without field codes."""
    name, command, in_entry = "", [], False
    for line in text.splitlines():
        if line.startswith("["):
            in_entry = line.strip() == "[Desktop Entry]"
        elif in_entry and line.startswith("Name=") and not name:
            name = line[len("Name="):].strip()
        elif in_entry and line.startswith("Exec=") and not command:
            command = [arg for arg in shlex.split(line[len("Exec="):]) if not re.fullmatch(r"%[a-zA-Z]", arg)]
    while command[:1] == ["env"] or (command and "=" in command[0] and not command[0].startswith("/")):
        command = command[1:]  # env FOO=bar app ...
    return name, command


def find_launcher_by_name(query: str) -> Path | None:
    """A system launcher by file name (spotify, spotify.desktop) or display name."""
    stem = query.removesuffix(".desktop")
    candidates = []
    for base in _data_dirs():
        directory = base / "applications"
        if (directory / f"{stem}.desktop").exists():
            return directory / f"{stem}.desktop"
        if directory.is_dir():
            candidates += sorted(directory.glob("*.desktop"))
    for path in candidates:
        try:
            name, _ = _launcher_command(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            continue
        if name.lower() == query.lower():
            return path
    return None


def add_custom(query: str, process: str = "") -> App:
    """Remember an app from its launcher so ``open`` and ``apps setup`` handle it."""
    path = find_launcher_by_name(query)
    if path is None:
        raise AddError(
            f"No app launcher called '{query}' found. Use the name from your app menu, "
            "or the launcher's file name from /usr/share/applications."
        )
    name, command = _launcher_command(path.read_text(encoding="utf-8"))
    if not command:
        raise AddError(f"{path} has no command to start the app.")
    if os.path.basename(command[0]) == "flatpak":
        raise AddError("Flatpak apps can't be moved between desktops yet.")
    app_id = re.sub(r"[^a-z0-9.-]+", "-", path.stem.lower()).strip("-")
    if app_id in APPS:
        raise AddError(f"{APPS[app_id].name} is already built in. Run: desktop-switcher apps setup")
    if not process:
        binary = shutil.which(command[0])
        process = os.path.basename(os.path.realpath(binary)) if binary else os.path.basename(command[0])
    parser = _read_custom()
    parser[app_id] = {"name": name or app_id, "launcher": path.name, "command": shlex.join(command),
                      "process": process}
    _write_custom(parser)
    return custom_apps()[app_id]


def forget_custom(app_id: str) -> App | None:
    parser = _read_custom()
    app = custom_apps().get(app_id)
    if app is None:
        return None
    parser.remove_section(app_id)
    _write_custom(parser)
    return app


@dataclass
class Process:
    pid: int
    ppid: int
    exe: str
    env: dict[str, str] = field(default_factory=dict)


def _read_environ(pid: int, proc: Path) -> dict[str, str]:
    raw = (proc / str(pid) / "environ").read_bytes()
    env = {}
    for item in raw.split(b"\0"):
        key, sep, value = item.partition(b"=")
        if sep:
            env[key.decode(errors="replace")] = value.decode(errors="replace")
    return env


def user_processes(proc: Path = Path("/proc")) -> list[Process]:
    """Processes of the current user, with the parts of them we look at."""
    uid = os.getuid()
    found = []
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if entry.stat().st_uid != uid:
                continue
            exe = os.readlink(entry / "exe").removesuffix(" (deleted)")
            stat = (entry / "stat").read_text()
            ppid = int(stat.rsplit(")", 1)[1].split()[1])
            found.append(Process(int(entry.name), ppid, exe, _read_environ(int(entry.name), proc)))
        except (OSError, ValueError, IndexError):
            continue  # gone, or not ours to read
    return found


def display_of(env: dict[str, str]) -> tuple[str, str]:
    return env.get("WAYLAND_DISPLAY", ""), env.get("DISPLAY", "")


def same_desktop(env: dict[str, str], here: tuple[str, str]) -> bool | None:
    """True or False if we can tell where ``env`` belongs, None if we can't."""
    wayland, x11 = display_of(env)
    if wayland and here[0]:
        return wayland == here[0]
    if x11 and here[1]:
        return x11 == here[1]
    return None


def main_processes(app: App, processes: list[Process]) -> list[Process]:
    """The app's top processes: matching ones whose parent is not a match."""
    matching = {p.pid: p for p in processes if os.path.basename(p.exe) in app.exe_names}
    return [p for p in matching.values() if p.ppid not in matching]


def running_elsewhere(app: App, processes: list[Process], here: tuple[str, str]) -> list[Process]:
    return [p for p in main_processes(app, processes) if same_desktop(p.env, here) is False]


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # A process that has exited but not been reaped yet is a zombie.
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] != "Z"
    except (OSError, IndexError):
        return False


def close(app: App, targets: list[Process]) -> bool:
    """Ask the app to quit and wait for it. True once every target has exited."""
    if app.quit_command:
        try:
            subprocess.run(app.quit_command, env=targets[0].env, timeout=app.quit_timeout,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired):
            pass
    else:
        for p in targets:
            try:
                os.kill(p.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    deadline = time.monotonic() + app.quit_timeout
    while time.monotonic() < deadline:
        if not any(_alive(p.pid) for p in targets):
            return True
        time.sleep(0.2)
    return False


def notify(text: str) -> None:
    """Show a desktop notification; launchers have no terminal to print to."""
    try:
        subprocess.run(["notify-send", "--app-name=Desktop Switcher", text], timeout=5,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        pass


# Launcher overrides ------------------------------------------------------


def _data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"))


def _data_dirs() -> list[Path]:
    dirs = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    return [Path(d) for d in dirs.split(":") if d]


def find_system_launcher(app: App) -> Path | None:
    for base in _data_dirs():
        path = base / "applications" / app.desktop_file
        if path.exists():
            return path
    return None


def override_text(original: str, app: App) -> str:
    """Rewrite a .desktop file so every Exec line goes through ``open``."""
    out = []
    for line in original.splitlines():
        if line.startswith("Exec="):
            line = f"Exec=desktop-switcher open {app.id} -- {line[len('Exec='):]}"
        elif line.startswith("DBusActivatable="):
            continue  # would start the app without our Exec line
        out.append(line)
        if line.strip() == "[Desktop Entry]":
            out.append(f"{MARKER}={app.id}")
    return "\n".join(out) + "\n"


def user_launcher(app: App) -> Path:
    return _data_home() / "applications" / app.desktop_file


def is_ours(path: Path) -> bool:
    try:
        return any(line.startswith(f"{MARKER}=") for line in path.read_text(encoding="utf-8").splitlines())
    except OSError:
        return False


def setup_launcher(app: App) -> str:
    """Install the launcher override for ``app``. Returns a line for the user."""
    source = find_system_launcher(app)
    if source is None:
        return f"{app.name}: not installed, skipped."
    target = user_launcher(app)
    if target.exists() and not is_ours(target):
        return f"{app.name}: you already have your own launcher at {target}, so it was left alone."
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(override_text(source.read_text(encoding="utf-8"), app), encoding="utf-8")
    return f"{app.name}: set up. It now moves to the desktop you open it on."


def remove_launcher(app: App) -> str | None:
    target = user_launcher(app)
    if target.exists() and is_ours(target):
        target.unlink()
        return f"{app.name}: launcher restored."
    return None
