import tempfile
import unittest
from pathlib import Path

from desktop_switcher import sessions

PLASMA = """[Desktop Entry]
Exec=/usr/lib/plasma-dbus-run-session-if-needed /usr/bin/startplasma-wayland
TryExec=/usr/bin/startplasma-wayland
DesktopNames=KDE
Name=Plasma (Wayland)
"""

HYPRLAND = """[Desktop Entry]
Name=Hyprland
Comment=An intelligent dynamic tiling Wayland compositor
Exec=Hyprland %U
Type=Application
"""

HIDDEN = """[Desktop Entry]
Name=Old
Exec=old-session
Hidden=true
"""


class DiscoverTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.wayland = root / "wayland-sessions"
        self.x11 = root / "xsessions"
        self.wayland.mkdir()
        self.x11.mkdir()
        (self.wayland / "plasma.desktop").write_text(PLASMA)
        (self.wayland / "hyprland.desktop").write_text(HYPRLAND)
        (self.wayland / "old.desktop").write_text(HIDDEN)
        (self.x11 / "plasmax11.desktop").write_text(PLASMA.replace("wayland", "x11"))
        (self.x11 / "hyprland.desktop").write_text(HYPRLAND)

    def tearDown(self):
        self.tmp.cleanup()

    def discover(self):
        return sessions.discover((str(self.wayland),), (str(self.x11),))

    def test_finds_sessions_and_skips_hidden(self):
        found = self.discover()
        self.assertEqual(sorted(found), ["hyprland", "plasma", "plasmax11"])

    def test_wayland_wins_on_clash(self):
        self.assertEqual(self.discover()["hyprland"].type, "wayland")
        self.assertEqual(self.discover()["plasmax11"].type, "x11")

    def test_field_codes_dropped(self):
        self.assertEqual(self.discover()["hyprland"].exec, ("Hyprland",))

    def test_desktop_names(self):
        plasma = self.discover()["plasma"]
        self.assertEqual(plasma.desktop_names, ("KDE",))
        self.assertTrue(plasma.matches("KDE"))
        self.assertTrue(plasma.matches("plasma"))
        self.assertFalse(plasma.matches("GNOME"))
        self.assertFalse(plasma.matches(""))

    def test_missing_dirs_are_fine(self):
        self.assertEqual(sessions.discover(("/nonexistent",), ()), {})


class LaunchTest(unittest.TestCase):
    session = sessions.Session(
        id="plasma",
        name="Plasma (Wayland)",
        exec=("/usr/lib/plasma-dbus-run-session-if-needed", "/usr/bin/startplasma-wayland"),
        type="wayland",
        desktop_names=("KDE",),
    )

    def test_command_uses_private_bus(self):
        self.assertEqual(
            sessions.launch_command(self.session),
            [
                "dbus-run-session",
                "--",
                "/usr/lib/plasma-dbus-run-session-if-needed",
                "/usr/bin/startplasma-wayland",
            ],
        )

    def test_environment(self):
        env = sessions.launch_environment(
            self.session,
            {"HOME": "/home/j", "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus", "WAYLAND_DISPLAY": "wayland-0"},
        )
        self.assertEqual(env["HOME"], "/home/j")
        self.assertNotIn("DBUS_SESSION_BUS_ADDRESS", env)
        self.assertNotIn("WAYLAND_DISPLAY", env)
        self.assertEqual(env["XDG_SESSION_TYPE"], "wayland")
        self.assertEqual(env["XDG_SESSION_DESKTOP"], "plasma")
        self.assertEqual(env["XDG_CURRENT_DESKTOP"], "KDE")


if __name__ == "__main__":
    unittest.main()
