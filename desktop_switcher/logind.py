"""Read and change login sessions through systemd-logind's ``loginctl``."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Callable

Runner = Callable[[list[str]], str]

_PROPS = ("Id", "VTNr", "Active", "Desktop", "Type", "Class", "State", "Seat", "Remote")


def run(cmd: list[str]) -> str:
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


@dataclass(frozen=True)
class LoginSession:
    id: str
    vt: int
    active: bool
    desktop: str
    type: str
    klass: str
    state: str
    seat: str

    @property
    def graphical(self) -> bool:
        return self.type in ("wayland", "x11") and self.klass == "user"


def parse_properties(text: str) -> dict[str, str]:
    props = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            props[key.strip()] = value.strip()
    return props


def user_sessions(user: str, runner: Runner = run) -> list[LoginSession]:
    ids = runner(["loginctl", "show-user", user, "-p", "Sessions", "--value"]).split()
    sessions = []
    for sid in ids:
        args = ["loginctl", "show-session", sid]
        for prop in _PROPS:
            args += ["-p", prop]
        try:
            props = parse_properties(runner(args))
        except subprocess.CalledProcessError:
            continue  # session ended between the two calls
        if props.get("Remote") == "yes":
            continue
        sessions.append(
            LoginSession(
                id=props.get("Id", sid),
                vt=int(props.get("VTNr") or 0),
                active=props.get("Active") == "yes",
                desktop=props.get("Desktop", ""),
                type=props.get("Type", ""),
                klass=props.get("Class", ""),
                state=props.get("State", ""),
                seat=props.get("Seat", ""),
            )
        )
    return sessions


def activate(session_id: str, runner: Runner = run) -> None:
    """Bring a session to the screen, the same as switching virtual terminals."""
    runner(["loginctl", "activate", session_id])
