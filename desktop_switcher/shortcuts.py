"""Bind Super+S to ``desktop-switcher switch`` in the desktops we know how to configure."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

COMMAND = "desktop-switcher"
NIRI_BIND = 'Mod+S { spawn "desktop-switcher" "switch"; }'
PLASMA_KEY = "Meta+S"
PLASMA_GROUP = ("services", "desktop-switcher.desktop")

_BINDS_OPEN = re.compile(r"^(\s*)binds\s*\{\s*$")
_NIRI_MOD_S = re.compile(r"^\s*Mod\+S\s")


def _config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"))


def add_niri_bind(text: str) -> tuple[str, str]:
    """Return (new_text, status). Status is added, exists, conflict or no-binds."""
    lines = text.splitlines(keepends=True)
    if any(COMMAND in line and not line.lstrip().startswith("//") for line in lines):
        return text, "exists"
    if any(_NIRI_MOD_S.match(line) for line in lines):
        return text, "conflict"
    for i, line in enumerate(lines):
        match = _BINDS_OPEN.match(line)
        if match:
            indent = match.group(1) + "    "
            lines.insert(i + 1, f"{indent}{NIRI_BIND}\n")
            return "".join(lines), "added"
    return text, "no-binds"


def setup_niri() -> str:
    path = _config_home() / "niri" / "config.kdl"
    if not path.exists():
        return f"niri: no config at {path}. Log in to niri once so it creates one, then run this again."
    original = path.read_text(encoding="utf-8")
    updated, status = add_niri_bind(original)
    if status == "exists":
        return "niri: already set up."
    if status == "conflict":
        return "niri: Super+S is already used for something else in your niri config, so nothing was changed."
    if status == "no-binds":
        return f"niri: could not find the 'binds {{' section in {path}, so nothing was changed."

    backup = path.with_name(path.name + ".before-desktop-switcher")
    shutil.copy2(path, backup)
    path.write_text(updated, encoding="utf-8")
    if shutil.which("niri"):
        check = subprocess.run(["niri", "validate"], capture_output=True, text=True)
        if check.returncode != 0:
            shutil.copy2(backup, path)
            return "niri: the change made the config invalid, so it was undone. Nothing changed."
    return f"niri: added Super+S. Your old config is saved as {backup.name}."


def plasma_key_in_use(text: str, key: str = PLASMA_KEY) -> bool:
    """True if any shortcut in kglobalshortcutsrc already uses ``key``."""
    for line in text.splitlines():
        if line.startswith("[") or "=" not in line:
            continue
        value = line.split("=", 1)[1]
        active = value.split(",", 1)[0]  # "active,default,name" or just "active"
        if key in active.split("\t"):
            return True
    return False


def plasma_already_set(text: str) -> bool:
    header = "".join(f"[{part}]" for part in PLASMA_GROUP)
    return header in text


def setup_plasma() -> str:
    writer = shutil.which("kwriteconfig6")
    if writer is None:
        return "Plasma: kwriteconfig6 not found, so the shortcut was not set. Add it in System Settings instead."
    path = _config_home() / "kglobalshortcutsrc"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if plasma_already_set(text):
        return "Plasma: already set up."
    if plasma_key_in_use(text):
        return "Plasma: Meta+S is already used by a shortcut (maybe one you added yourself), so nothing was changed."
    args = [writer, "--file", "kglobalshortcutsrc"]
    for group in PLASMA_GROUP:
        args += ["--group", group]
    subprocess.run([*args, "--key", "_launch", PLASMA_KEY], check=True)
    return "Plasma: added Meta+S (Super+S). It works after you log out of Plasma and back in."


SETUP = {"niri": setup_niri, "plasma": setup_plasma}
