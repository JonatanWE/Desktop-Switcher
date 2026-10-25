"""Decide what a press of the switch button should do.

The model: the user logs in to one desktop of the pair through the normal
login screen (the *primary* session). The other desktop runs in a
*secondary* session that this tool starts on a fixed virtual terminal.
Switching only changes which session is on screen; both keep running, so
no window is closed.

``plan`` is a pure function so it can be tested without a real system.
"""

from __future__ import annotations

from dataclasses import dataclass

from .logind import LoginSession
from .sessions import Session


class SwitchError(Exception):
    pass


@dataclass(frozen=True)
class Plan:
    action: str  # "activate" or "start"
    target: str  # desktop id we switch to
    session_id: str = ""  # login session to activate, for "activate"


def current_desktop(
    current: LoginSession,
    secondary_vt: int,
    secondary_desktop: str,
    pair: tuple[str, str],
    installed: dict[str, Session],
) -> str:
    if current.vt == secondary_vt and secondary_desktop:
        return secondary_desktop
    for desktop_id in pair:
        session = installed.get(desktop_id)
        if session and session.matches(current.desktop):
            return desktop_id
        if current.desktop.lower() == desktop_id.lower():
            return desktop_id
    raise SwitchError(
        f"This session's desktop ({current.desktop or 'unknown'}) is not one of the "
        f"pair {pair[0]} / {pair[1]}. Log in to one of them, or change the pair."
    )


def plan(
    pair: tuple[str, str],
    sessions: list[LoginSession],
    current_session_id: str,
    secondary_vt: int,
    secondary_desktop: str,
    installed: dict[str, Session],
) -> Plan:
    graphical = [s for s in sessions if s.graphical and s.state != "closing"]
    current = next((s for s in graphical if s.id == current_session_id), None)
    if current is None:
        current = next((s for s in graphical if s.active), None)
    if current is None:
        raise SwitchError("Could not find the graphical session you are in.")

    here = current_desktop(current, secondary_vt, secondary_desktop, pair, installed)
    target = pair[1] if here == pair[0] else pair[0]

    if current.vt == secondary_vt:
        # We are in the secondary desktop; go back to the login-screen one.
        primary = next((s for s in graphical if s.vt != secondary_vt), None)
        if primary is None:
            raise SwitchError(
                "The desktop you logged in with is no longer running. "
                "Log in again from the login screen."
            )
        return Plan("activate", target, primary.id)

    secondary = next((s for s in graphical if s.vt == secondary_vt), None)
    if secondary is not None:
        if secondary_desktop and secondary_desktop != target:
            raise SwitchError(
                f"The background session is running {secondary_desktop}, not {target}. "
                "Run 'desktop-switcher stop' first."
            )
        return Plan("activate", target, secondary.id)
    return Plan("start", target)
