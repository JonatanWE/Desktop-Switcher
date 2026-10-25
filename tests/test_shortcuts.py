import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from desktop_switcher import shortcuts

NIRI = """input {
    keyboard {}
}

binds {
    Mod+T { spawn "alacritty"; }
}
"""


class NiriTest(unittest.TestCase):
    def test_adds_bind_inside_binds_block(self):
        text, status = shortcuts.add_niri_bind(NIRI)
        self.assertEqual(status, "added")
        self.assertIn('binds {\n    Mod+S { spawn "desktop-switcher" "switch"; }\n    Mod+T', text)

    def test_existing_bind_left_alone(self):
        text, _ = shortcuts.add_niri_bind(NIRI)
        self.assertEqual(shortcuts.add_niri_bind(text), (text, "exists"))

    def test_commented_bind_does_not_count(self):
        text = NIRI.replace("binds {\n", 'binds {\n    // Mod+X { spawn "desktop-switcher" "switch"; }\n')
        self.assertEqual(shortcuts.add_niri_bind(text)[1], "added")

    def test_conflict(self):
        text = NIRI.replace("Mod+T", "Mod+S")
        self.assertEqual(shortcuts.add_niri_bind(text), (text, "conflict"))

    def test_no_binds(self):
        self.assertEqual(shortcuts.add_niri_bind("input {}\n")[1], "no-binds")

    def test_setup_restores_backup_when_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "niri" / "config.kdl"
            path.parent.mkdir()
            path.write_text(NIRI)
            invalid = mock.Mock(returncode=1)
            with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp}), mock.patch.object(
                shortcuts.shutil, "which", return_value="/usr/bin/niri"
            ), mock.patch.object(shortcuts.subprocess, "run", return_value=invalid):
                message = shortcuts.setup_niri()
            self.assertIn("undone", message)
            self.assertEqual(path.read_text(), NIRI)

    def test_setup_adds_and_keeps_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "niri" / "config.kdl"
            path.parent.mkdir()
            path.write_text(NIRI)
            with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp}), mock.patch.object(
                shortcuts.shutil, "which", return_value=None
            ):
                message = shortcuts.setup_niri()
            self.assertIn("added", message)
            self.assertIn("desktop-switcher", path.read_text())
            self.assertEqual((path.parent / "config.kdl.before-desktop-switcher").read_text(), NIRI)


class PlasmaTest(unittest.TestCase):
    RC = (
        "[services][org.kde.konsole.desktop]\n_launch=Ctrl+Alt+T\n\n"
        "[kwin]\nOverview=Meta+W\tMeta+Tab,Meta+W,Toggle Overview\n"
        "Unused=none,Meta+S,Something\n"
    )

    def test_key_in_use(self):
        self.assertTrue(shortcuts.plasma_key_in_use(self.RC, "Meta+Tab"))
        self.assertTrue(shortcuts.plasma_key_in_use(self.RC, "Ctrl+Alt+T"))
        # Only the active binding counts, not the default column.
        self.assertFalse(shortcuts.plasma_key_in_use(self.RC, "Meta+S"))

    def test_already_set(self):
        self.assertFalse(shortcuts.plasma_already_set(self.RC))
        self.assertTrue(shortcuts.plasma_already_set("[services][desktop-switcher.desktop]\n_launch=Meta+S\n"))


if __name__ == "__main__":
    unittest.main()
