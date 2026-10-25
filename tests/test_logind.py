import subprocess
import unittest

from desktop_switcher import logind

SESSIONS = {
    "2": "Id=2\nVTNr=2\nActive=yes\nDesktop=KDE\nType=wayland\nClass=user\nState=active\nSeat=seat0\nRemote=no\n",
    "5": "Id=5\nVTNr=8\nActive=no\nDesktop=\nType=wayland\nClass=user\nState=online\nSeat=seat0\nRemote=no\n",
    "7": "Id=7\nVTNr=0\nActive=no\nDesktop=\nType=tty\nClass=user\nState=online\nSeat=\nRemote=yes\n",
}


def fake_runner(cmd):
    if cmd[:2] == ["loginctl", "show-user"]:
        return "2 5 7 9\n"
    if cmd[:2] == ["loginctl", "show-session"]:
        sid = cmd[2]
        if sid not in SESSIONS:
            raise subprocess.CalledProcessError(1, cmd)
        return SESSIONS[sid]
    raise AssertionError(cmd)


class LogindTest(unittest.TestCase):
    def test_user_sessions(self):
        found = logind.user_sessions("jonatan", fake_runner)
        # 7 is remote (ssh), 9 vanished between calls
        self.assertEqual([s.id for s in found], ["2", "5"])
        self.assertTrue(found[0].active)
        self.assertEqual(found[1].vt, 8)
        self.assertTrue(all(s.graphical for s in found))

    def test_parse_properties_ignores_junk(self):
        self.assertEqual(logind.parse_properties("A=1\nnoise\nB = x=y\n"), {"A": "1", "B": "x=y"})

    def test_activate(self):
        calls = []
        logind.activate("5", lambda cmd: calls.append(cmd) or "")
        self.assertEqual(calls, [["loginctl", "activate", "5"]])


if __name__ == "__main__":
    unittest.main()
