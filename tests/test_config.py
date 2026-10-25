import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from desktop_switcher import config


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        env = {"XDG_CONFIG_HOME": self.tmp.name + "/cfg", "XDG_STATE_HOME": self.tmp.name + "/state"}
        self.env = mock.patch.dict(os.environ, env)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_round_trip(self):
        self.assertIsNone(config.load().pair)
        config.save(config.Config("hyprland", "plasma"))
        self.assertEqual(config.load().pair, ("hyprland", "plasma"))

    def test_secondary_state(self):
        self.assertEqual(config.read_secondary_desktop(), "")
        config.write_secondary_desktop("plasma")
        self.assertEqual(config.read_secondary_desktop(), "plasma")

    def test_secondary_vt(self):
        path = Path(self.tmp.name) / "ds.conf"
        self.assertEqual(config.secondary_vt(path), config.DEFAULT_VT)
        path.write_text("[secondary]\nvt = 9\n")
        self.assertEqual(config.secondary_vt(path), 9)


if __name__ == "__main__":
    unittest.main()
