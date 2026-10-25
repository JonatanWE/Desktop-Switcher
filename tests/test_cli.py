import unittest
from unittest import mock

from desktop_switcher import cli
from desktop_switcher.logind import LoginSession

BACKGROUND = LoginSession("19", 8, False, "", "wayland", "user", "online", "seat0")


class WaitForSecondaryTest(unittest.TestCase):
    def setUp(self):
        for name, value in (("SETTLE_TIME", 0.05), ("START_TIMEOUT", 1.0)):
            patcher = mock.patch.object(cli, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(cli.time, "sleep", lambda s: None)
        # Real sleeps are skipped, so time only advances through monotonic().
        clock = iter(i * 0.01 for i in range(10_000))
        self.addCleanup(patcher.stop)
        patcher.start()
        patcher = mock.patch.object(cli.time, "monotonic", lambda: next(clock))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_returns_session_that_stays_up(self):
        with mock.patch.object(cli, "_unit_active", return_value=True), mock.patch.object(
            cli.logind, "user_sessions", return_value=[BACKGROUND]
        ):
            self.assertEqual(cli._wait_for_secondary("j", 8), BACKGROUND)

    def test_desktop_that_dies_is_never_activated(self):
        # Session appears, then the unit exits before the settle time is up.
        alive = iter([True, True, False])
        with mock.patch.object(cli, "_unit_active", side_effect=lambda user: next(alive)), mock.patch.object(
            cli.logind, "user_sessions", return_value=[BACKGROUND]
        ):
            self.assertIsNone(cli._wait_for_secondary("j", 8))

    def test_times_out_without_session(self):
        with mock.patch.object(cli, "_unit_active", return_value=True), mock.patch.object(
            cli.logind, "user_sessions", return_value=[]
        ):
            self.assertIsNone(cli._wait_for_secondary("j", 8))


if __name__ == "__main__":
    unittest.main()
