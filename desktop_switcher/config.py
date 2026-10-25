"""User settings (the desktop pair) and system settings (the secondary VT)."""

from __future__ import annotations

import configparser
import os
from dataclasses import dataclass
from pathlib import Path

SYSTEM_CONFIG = Path("/etc/desktop-switcher.conf")
DEFAULT_VT = 8


def user_config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "desktop-switcher" / "config.ini"


def state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return Path(base) / "desktop-switcher"


@dataclass
class Config:
    desktop_a: str = ""
    desktop_b: str = ""

    @property
    def pair(self) -> tuple[str, str] | None:
        if self.desktop_a and self.desktop_b:
            return self.desktop_a, self.desktop_b
        return None


def load(path: Path | None = None) -> Config:
    path = path or user_config_path()
    parser = configparser.ConfigParser()
    parser.read(path)
    return Config(
        desktop_a=parser.get("pair", "a", fallback=""),
        desktop_b=parser.get("pair", "b", fallback=""),
    )


def save(cfg: Config, path: Path | None = None) -> Path:
    path = path or user_config_path()
    parser = configparser.ConfigParser()
    parser["pair"] = {"a": cfg.desktop_a, "b": cfg.desktop_b}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        parser.write(fh)
    return path


def secondary_vt(path: Path = SYSTEM_CONFIG) -> int:
    parser = configparser.ConfigParser()
    parser.read(path)
    return parser.getint("secondary", "vt", fallback=DEFAULT_VT)


def read_secondary_desktop() -> str:
    """Which desktop the secondary session was last started with."""
    try:
        return (state_dir() / "secondary").read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def write_secondary_desktop(session_id: str) -> None:
    directory = state_dir()
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "secondary").write_text(session_id + "\n", encoding="utf-8")
