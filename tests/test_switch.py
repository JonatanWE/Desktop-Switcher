import unittest

from desktop_switcher.logind import LoginSession
from desktop_switcher.sessions import Session
from desktop_switcher.switch import Plan, SwitchError, plan

INSTALLED = {
    "plasma": Session("plasma", "Plasma (Wayland)", ("startplasma-wayland",), "wayland", ("KDE",)),
    "hyprland": Session("hyprland", "Hyprland", ("Hyprland",), "wayland"),
}
PAIR = ("hyprland", "plasma")
VT = 8


def login(sid, vt, desktop="", active=False, type_="wayland"):
    return LoginSession(sid, vt, active, desktop, type_, "user", "active" if active else "online", "seat0")


class PlanTest(unittest.TestCase):
    def test_starts_secondary_when_not_running(self):
        sessions = [login("2", 2, "Hyprland", active=True)]
        self.assertEqual(plan(PAIR, sessions, "2", VT, "", INSTALLED), Plan("start", "plasma"))

    def test_matches_desktop_names(self):
        sessions = [login("2", 2, "KDE", active=True)]
        self.assertEqual(plan(PAIR, sessions, "2", VT, "", INSTALLED), Plan("start", "hyprland"))

    def test_activates_running_secondary(self):
        sessions = [login("2", 2, "hyprland", active=True), login("5", VT)]
        self.assertEqual(plan(PAIR, sessions, "2", VT, "plasma", INSTALLED), Plan("activate", "plasma", "5"))

    def test_from_secondary_back_to_primary(self):
        sessions = [login("2", 2, "hyprland"), login("5", VT, active=True)]
        self.assertEqual(plan(PAIR, sessions, "5", VT, "plasma", INSTALLED), Plan("activate", "hyprland", "2"))

    def test_falls_back_to_active_session(self):
        sessions = [login("2", 2, "hyprland", active=True)]
        self.assertEqual(plan(PAIR, sessions, "", VT, "", INSTALLED).action, "start")

    def test_ignores_tty_sessions(self):
        sessions = [login("1", 3, type_="tty", active=True)]
        with self.assertRaises(SwitchError):
            plan(PAIR, sessions, "1", VT, "", INSTALLED)

    def test_unknown_desktop(self):
        sessions = [login("2", 2, "GNOME", active=True)]
        with self.assertRaisesRegex(SwitchError, "not one of the pair"):
            plan(PAIR, sessions, "2", VT, "", INSTALLED)

    def test_secondary_running_wrong_desktop(self):
        # Logged in to plasma, but the background session also runs plasma.
        sessions = [login("2", 2, "KDE", active=True), login("5", VT)]
        with self.assertRaisesRegex(SwitchError, "desktop-switcher stop"):
            plan(PAIR, sessions, "2", VT, "plasma", INSTALLED)

    def test_primary_gone(self):
        sessions = [login("5", VT, active=True)]
        with self.assertRaisesRegex(SwitchError, "login screen"):
            plan(PAIR, sessions, "5", VT, "plasma", INSTALLED)


if __name__ == "__main__":
    unittest.main()
