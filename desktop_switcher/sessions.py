"""Discover the desktop sessions installed on this system.

Display managers list desktops from ``.desktop`` files in
``/usr/share/wayland-sessions`` and ``/usr/share/xsessions``. We read the
same files, so any desktop the login screen offers can be part of a pair.
"""

from __future__ import annotations

import configparser
import os
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path

WAYLAND_DIRS = ("/usr/share/wayland-sessions", "/usr/local/share/wayland-sessions")
X11_DIRS = ("/usr/share/xsessions", "/usr/local/share/xsessions")

# Field codes such as %f or %U are meaningless for sessions; drop them.
_FIELD_CODE = re.compile(r"^%[a-zA-Z]$")


@dataclass(frozen=True)
class Session:
    id: str  # file name without .desktop, e.g. "plasma" or "hyprland"
    name: str  # human name, e.g. "Plasma (Wayland)"
    exec: tuple[str, ...]
    type: str  # "wayland" or "x11"
    desktop_names: tuple[str, ...] = field(default_factory=tuple)
    path: str = ""

    def matches(self, value: str) -> bool:
        """True if a logind Desktop= or XDG_CURRENT_DESKTOP value names this session."""
        if not value:
            return False
        wanted = {v.strip().lower() for v in value.split(":") if v.strip()}
        known = {self.id.lower(), *(d.lower() for d in self.desktop_names)}
        return bool(wanted & known)


def parse_exec(value: str) -> tuple[str, ...]:
    return tuple(arg for arg in shlex.split(value) if not _FIELD_CODE.match(arg))


def parse_session_file(path: Path, session_type: str) -> Session | None:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str  # keep key case
    try:
        parser.read(path, encoding="utf-8")
    except (configparser.Error, UnicodeDecodeError):
        return None
    if not parser.has_section("Desktop Entry"):
        return None
    entry = parser["Desktop Entry"]
    if entry.get("Hidden", "false").lower() == "true":
        return None
    if entry.get("NoDisplay", "false").lower() == "true":
        return None
    exec_value = entry.get("Exec", "").strip()
    if not exec_value:
        return None
    names = tuple(n for n in entry.get("DesktopNames", "").split(";") if n)
    return Session(
        id=path.stem,
        name=entry.get("Name", path.stem),
        exec=parse_exec(exec_value),
        type=session_type,
        desktop_names=names,
        path=str(path),
    )


def discover(
    wayland_dirs: tuple[str, ...] = WAYLAND_DIRS,
    x11_dirs: tuple[str, ...] = X11_DIRS,
) -> dict[str, Session]:
    """Return installed sessions keyed by id. Wayland wins over X11 on a name clash."""
    found: dict[str, Session] = {}
    for dirs, kind in ((x11_dirs, "x11"), (wayland_dirs, "wayland")):
        for directory in dirs:
            if not os.path.isdir(directory):
                continue
            for path in sorted(Path(directory).glob("*.desktop")):
                session = parse_session_file(path, kind)
                if session:
                    found[session.id] = session
    return found


class NotBackgroundCapable(Exception):
    pass


def background_exec(session: Session) -> tuple[str, ...]:
    """The command that runs ``session`` as the background desktop.

    Some login entries do not start the compositor themselves: they hand it
    to the user's systemd manager, which is shared with the desktop already
    running. ``niri-session`` is one: it runs niri as niri.service outside
    our login session, and when it ends it stops graphical-session.target,
    which also ends the other desktop (you get logged out). For those we
    start the compositor directly, or refuse if we cannot.
    """
    names = [os.path.basename(arg) for arg in session.exec]
    if not names:
        raise NotBackgroundCapable(f"{session.name} has no command to run.")
    if names[0] == "niri-session":
        return ("niri",)
    if names[0] == "uwsm":
        raise NotBackgroundCapable(
            f"{session.name} starts through uwsm, which cannot run next to another desktop. "
            "Pair the entry without uwsm instead (see 'desktop-switcher list')."
        )
    if "startplasma-wayland" in names:
        raise NotBackgroundCapable(
            "KDE Plasma cannot be the background desktop yet. "
            "Log in to Plasma from the login screen and switch to the other desktop from there."
        )
    if "gnome-session" in names:
        raise NotBackgroundCapable(
            "GNOME cannot be the background desktop. "
            "Log in to GNOME from the login screen and switch to the other desktop from there."
        )
    return session.exec


def launch_command(session: Session) -> list[str]:
    """Command that starts ``session`` on its own private D-Bus session bus.

    Both desktops run as the same user, so they would otherwise share the
    user's session bus and fight over service names (two plasmashells, two
    notification daemons). ``dbus-run-session`` gives this desktop its own bus.
    """
    return ["dbus-run-session", "--", *background_exec(session)]


def launch_environment(session: Session, base: dict[str, str]) -> dict[str, str]:
    env = {
        k: v
        for k, v in base.items()
        if k not in ("DBUS_SESSION_BUS_ADDRESS", "WAYLAND_DISPLAY", "DISPLAY")
    }
    env["XDG_SESSION_TYPE"] = session.type
    env["XDG_SESSION_DESKTOP"] = session.id
    if session.desktop_names:
        env["XDG_CURRENT_DESKTOP"] = ":".join(session.desktop_names)
    return env
