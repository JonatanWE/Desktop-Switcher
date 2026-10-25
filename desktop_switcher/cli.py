"""Command line interface: ``desktop-switcher <command>``."""

from __future__ import annotations

import argparse
import getpass
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import apps, config, logind, sessions, shortcuts
from .switch import SwitchError, plan

UNIT_FILE = Path("/etc/systemd/system/desktop-switcher-secondary@.service")
POLKIT_RULE = Path("/etc/polkit-1/rules.d/50-desktop-switcher.rules")
START_TIMEOUT = 20.0
SETTLE_TIME = 2.0


def unit_name(user: str) -> str:
    return f"desktop-switcher-secondary@{user}.service"


def _pair_or_exit(cfg: config.Config) -> tuple[str, str]:
    if not cfg.pair:
        sys.exit("No desktop pair set. Run: desktop-switcher pair <desktop-a> <desktop-b>")
    return cfg.pair


def cmd_list(args: argparse.Namespace) -> int:
    installed = sessions.discover()
    if not installed:
        print("No desktop sessions found in /usr/share/wayland-sessions or /usr/share/xsessions.")
        return 1
    width = max(len(s) for s in installed)
    for sid, session in sorted(installed.items()):
        note = "" if session.type == "wayland" else "  (X11, not supported yet)"
        print(f"{sid:<{width}}  {session.name}{note}")
    return 0


def cmd_pair(args: argparse.Namespace) -> int:
    installed = sessions.discover()
    for desktop in (args.a, args.b):
        if desktop not in installed:
            sys.exit(f"Unknown desktop '{desktop}'. See 'desktop-switcher list'.")
        if installed[desktop].type != "wayland":
            sys.exit(f"'{desktop}' is an X11 session; only Wayland desktops are supported for now.")
    if args.a == args.b:
        sys.exit("Pick two different desktops.")
    path = config.save(config.Config(args.a, args.b))
    print(f"Pair saved to {path}: {args.a} <-> {args.b}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    cfg = config.load()
    vt = config.secondary_vt()
    user = getpass.getuser()
    print(f"Pair: {cfg.desktop_a or '-'} <-> {cfg.desktop_b or '-'}")
    print(f"Background desktop VT: {vt}")
    for s in logind.user_sessions(user):
        if not s.graphical:
            continue
        role = "background" if s.vt == vt else "main, from login screen"
        desktop = config.read_secondary_desktop() if s.vt == vt else s.desktop
        mark = "*" if s.active else " "
        print(f"{mark} session {s.id}: VT {s.vt}, {desktop or 'unknown'} ({role})")
    return 0


def _unit_active(user: str) -> bool:
    result = subprocess.run(["systemctl", "is-active", "--quiet", unit_name(user)])
    return result.returncode == 0


def _wait_for_secondary(user: str, vt: int) -> logind.LoginSession | None:
    """Wait until the background desktop has a session and keeps running.

    Switching the screen to a desktop that has already died leaves you on an
    empty terminal, so we only return once it has stayed up for SETTLE_TIME.
    """
    deadline = time.monotonic() + START_TIMEOUT
    found: logind.LoginSession | None = None
    alive_since = 0.0
    while time.monotonic() < deadline:
        if not _unit_active(user):
            return None
        if found is None:
            found = next((s for s in logind.user_sessions(user) if s.vt == vt and s.graphical), None)
            alive_since = time.monotonic()
        elif time.monotonic() - alive_since >= SETTLE_TIME:
            return found
        time.sleep(0.25)
    return None


def cmd_switch(args: argparse.Namespace) -> int:
    cfg = config.load()
    pair = _pair_or_exit(cfg)
    vt = config.secondary_vt()
    user = getpass.getuser()
    installed = sessions.discover()
    try:
        step = plan(
            pair,
            logind.user_sessions(user),
            os.environ.get("XDG_SESSION_ID", ""),
            vt,
            config.read_secondary_desktop(),
            installed,
        )
    except SwitchError as err:
        sys.exit(str(err))

    if args.dry_run:
        print(f"Would {step.action} {step.target}" + (f" (session {step.session_id})" if step.session_id else ""))
        return 0

    if step.action == "activate":
        logind.activate(step.session_id)
        return 0

    target = installed.get(step.target)
    if target is None:
        sys.exit(f"'{step.target}' is not installed. See 'desktop-switcher list'.")
    try:
        sessions.launch_command(target)
    except sessions.NotBackgroundCapable as err:
        sys.exit(str(err))

    config.write_secondary_desktop(step.target)
    print(f"Starting {target.name} in the background...", flush=True)
    subprocess.run(["systemctl", "start", unit_name(user)], check=True)
    started = _wait_for_secondary(user, vt)
    if started is None:
        subprocess.run(["systemctl", "stop", unit_name(user)])
        sys.exit(
            f"{target.name} did not start, so the screen was not switched. "
            f"See what happened with: journalctl -b -u {unit_name(user)}"
        )
    logind.activate(started.id)
    return 0


def cmd_shortcut(args: argparse.Namespace) -> int:
    pair = _pair_or_exit(config.load())
    for desktop in pair:
        setup = shortcuts.SETUP.get(desktop)
        if setup is None:
            print(
                f"{desktop}: set this up by hand. Bind a key to the command "
                "'desktop-switcher switch' in its keyboard settings."
            )
        else:
            print(setup())
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    subprocess.run(["systemctl", "stop", unit_name(getpass.getuser())], check=True)
    print("Background desktop stopped. Apps that were open in it have closed.")
    return 0


def cmd_open(args: argparse.Namespace) -> int:
    """Start an app here, first closing it on the other desktop if it runs there."""
    app = apps.APPS[args.app]
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    command = command or list(app.command)
    here = apps.display_of(dict(os.environ))
    elsewhere = apps.running_elsewhere(app, apps.user_processes(), here)
    if elsewhere:
        apps.notify(f"Moving {app.name} from the other desktop...")
        if not apps.close(app, elsewhere):
            apps.notify(f"{app.name} is still closing on the other desktop. Try again in a moment.")
            return 1
        command += [arg for arg in app.restore_args if arg not in command]
    try:
        os.execvp(command[0], command)
    except OSError as err:
        apps.notify(f"Could not start {app.name}: {err}")
        return 1


def cmd_apps(args: argparse.Namespace) -> int:
    if args.action == "setup":
        for app in apps.APPS.values():
            print(apps.setup_launcher(app))
        return 0
    if args.action == "remove":
        lines = [line for app in apps.APPS.values() if (line := apps.remove_launcher(app))]
        print("\n".join(lines) or "Nothing to remove.")
        return 0
    here = apps.display_of(dict(os.environ))
    processes = apps.user_processes()
    for app in apps.APPS.values():
        if apps.find_system_launcher(app) is None:
            continue
        mains = apps.main_processes(app, processes)
        places = {apps.same_desktop(p.env, here) for p in mains}
        where = (
            "not running" if not mains
            else "running on the other desktop" if places == {False}
            else "running here"
        )
        moves = "moves" if apps.is_ours(apps.user_launcher(app)) else "does not move (run: desktop-switcher apps setup)"
        print(f"{app.name}: {where}, {moves}")
    return 0


def cmd_run_secondary(args: argparse.Namespace) -> int:
    """Entry point of the systemd unit: run the desktop and report how it ended.

    The desktop runs as a child rather than replacing this process, so its
    exit status always reaches the journal. Output of a process that exits
    immediately can otherwise be lost from ``journalctl -u``.
    """
    desktop = config.read_secondary_desktop()
    session = sessions.discover().get(desktop)
    if session is None:
        print(f"unknown desktop '{desktop}'", file=sys.stderr, flush=True)
        return 1
    try:
        command = sessions.launch_command(session)
    except sessions.NotBackgroundCapable as err:
        print(err, file=sys.stderr, flush=True)
        return 1
    print(
        f"starting {session.name}: {' '.join(command)} "
        f"(session {os.environ.get('XDG_SESSION_ID', '?')}, VT {os.environ.get('XDG_VTNR', '?')})",
        flush=True,
    )
    started = time.monotonic()
    result = subprocess.run(command, env=sessions.launch_environment(session, dict(os.environ)))
    print(f"{session.name} exited with status {result.returncode} after {time.monotonic() - started:.1f}s", flush=True)
    return result.returncode


def _can_background(session: sessions.Session) -> bool:
    try:
        sessions.launch_command(session)
        return True
    except sessions.NotBackgroundCapable:
        return False


def _check(ok: bool, text: str, hint: str = "") -> bool:
    print(f"[{'ok' if ok else '!!'}] {text}")
    if not ok and hint:
        print(f"     {hint}")
    return ok


def cmd_doctor(args: argparse.Namespace) -> int:
    good = True
    good &= _check(UNIT_FILE.exists(), "background session unit installed", "Run: sudo ./install.sh")
    good &= _check(POLKIT_RULE.exists(), "permission rule installed", "Run: sudo ./install.sh")
    good &= _check(bool(shutil.which("dbus-run-session")), "dbus-run-session available", "Install the 'dbus' package.")

    cfg = config.load()
    installed = sessions.discover()
    if _check(bool(cfg.pair), "desktop pair set", "Run: desktop-switcher pair <a> <b>"):
        for desktop in cfg.pair:
            if not _check(desktop in installed, f"'{desktop}' is installed", "See: desktop-switcher list"):
                good = False
                continue
            try:
                command = sessions.launch_command(installed[desktop])
                print(f"     '{desktop}' can run in the background as: {' '.join(command)}")
            except sessions.NotBackgroundCapable as err:
                print(f"     '{desktop}' must be the one you log in to: {err}")
        background_capable = [d for d in cfg.pair if d in installed and _can_background(installed[d])]
        good &= _check(
            bool(background_capable),
            "at least one desktop of the pair can run in the background",
            "Pair a standalone compositor such as niri, Hyprland or Sway.",
        )
    else:
        good = False

    if Path("/sys/module/nvidia_drm").exists():
        modeset = Path("/sys/module/nvidia_drm/parameters/modeset")
        on = modeset.exists() and modeset.read_text().strip() == "Y"
        good &= _check(on, "NVIDIA kernel modesetting on", "Add nvidia_drm.modeset=1 to the kernel command line.")
        params = Path("/proc/driver/nvidia/params")
        preserve = params.exists() and "PreserveVideoMemoryAllocations: 1" in params.read_text()
        _check(
            preserve,
            "NVIDIA preserves video memory across VT switches",
            "Recommended: options nvidia NVreg_PreserveVideoMemoryAllocations=1",
        )
    return 0 if good else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="desktop-switcher",
        description="Switch between two desktops that keep running side by side.",
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="command")

    sub.add_parser("list", help="list installed desktops").set_defaults(func=cmd_list)

    p = sub.add_parser("pair", help="choose the two desktops to switch between")
    p.add_argument("a")
    p.add_argument("b")
    p.set_defaults(func=cmd_pair)

    sub.add_parser("status", help="show running desktops").set_defaults(func=cmd_status)

    p = sub.add_parser("switch", help="switch to the other desktop, starting it if needed")
    p.add_argument("--dry-run", action="store_true", help="print what would happen")
    p.set_defaults(func=cmd_switch)

    sub.add_parser("shortcut", help="bind Super+S to switch in both desktops").set_defaults(func=cmd_shortcut)
    sub.add_parser("stop", help="stop the background desktop").set_defaults(func=cmd_stop)
    sub.add_parser("doctor", help="check the setup").set_defaults(func=cmd_doctor)

    p = sub.add_parser("apps", help="show or set up apps that move to the desktop you open them on")
    p.add_argument("action", nargs="?", choices=["setup", "remove"],
                   help="setup: make app launchers move the app; remove: undo that")
    p.set_defaults(func=cmd_apps)

    p = sub.add_parser("open", help="open an app here, closing it on the other desktop first")
    p.add_argument("app", choices=sorted(apps.APPS))
    p.add_argument("command", nargs=argparse.REMAINDER, help="-- the command to run (default: the app's own)")
    p.set_defaults(func=cmd_open)

    # Used by the systemd unit only.
    sub.add_parser("_run-secondary").set_defaults(func=cmd_run_secondary)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except subprocess.CalledProcessError as err:
        sys.exit(f"Command failed: {' '.join(err.cmd)}\n{(err.stderr or '').strip()}")
