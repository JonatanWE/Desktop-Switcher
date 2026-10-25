import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from desktop_switcher import apps, cli
from desktop_switcher.apps import Process

CHROME = apps.APPS["chrome"]
HERE = ("wayland-0", ":0")
THERE = {"WAYLAND_DISPLAY": "wayland-1", "DISPLAY": ":1"}
LOCAL = {"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0"}

DESKTOP_FILE = """[Desktop Entry]
Name=Google Chrome
Exec=/usr/bin/google-chrome-stable %U
DBusActivatable=true
Actions=new-window

[Desktop Action new-window]
Exec=/usr/bin/google-chrome-stable --new-window
"""


class DesktopTest(unittest.TestCase):
    def test_same_desktop_by_wayland_display(self):
        self.assertTrue(apps.same_desktop(LOCAL, HERE))
        self.assertFalse(apps.same_desktop(THERE, HERE))

    def test_falls_back_to_x11_display(self):
        self.assertFalse(apps.same_desktop({"DISPLAY": ":1"}, HERE))
        self.assertTrue(apps.same_desktop({"DISPLAY": ":0"}, ("", ":0")))

    def test_unknown_is_none(self):
        self.assertIsNone(apps.same_desktop({}, HERE))
        self.assertIsNone(apps.same_desktop(THERE, ("", "")))


class ProcessTest(unittest.TestCase):
    PROCESSES = [
        Process(100, 1, "/opt/google/chrome/chrome", THERE),
        Process(101, 100, "/opt/google/chrome/chrome", THERE),  # renderer
        Process(102, 100, "/opt/google/chrome/chrome_crashpad_handler", THERE),
        Process(200, 1, "/usr/bin/fish", LOCAL),
    ]

    def test_main_process_only(self):
        self.assertEqual([p.pid for p in apps.main_processes(CHROME, self.PROCESSES)], [100])

    def test_running_elsewhere(self):
        self.assertEqual([p.pid for p in apps.running_elsewhere(CHROME, self.PROCESSES, HERE)], [100])
        self.assertEqual(apps.running_elsewhere(CHROME, self.PROCESSES, ("wayland-1", ":1")), [])

    def test_unknown_desktop_is_left_alone(self):
        processes = [Process(100, 1, "/opt/google/chrome/chrome", {})]
        self.assertEqual(apps.running_elsewhere(CHROME, processes, HERE), [])


class FirefoxTest(unittest.TestCase):
    def test_content_processes_are_not_main(self):
        processes = [
            Process(300, 1, "/usr/lib/firefox/firefox", THERE),
            Process(301, 300, "/usr/lib/firefox/firefox", THERE),
        ]
        self.assertEqual([p.pid for p in apps.running_elsewhere(apps.APPS["firefox"], processes, HERE)], [300])


class OpenTest(unittest.TestCase):
    def run_open(self, argv, elsewhere, closed=True):
        with mock.patch.dict(os.environ, {"WAYLAND_DISPLAY": "wayland-0"}), mock.patch.object(
            apps, "user_processes", return_value=[]
        ), mock.patch.object(apps, "running_elsewhere", return_value=elsewhere), mock.patch.object(
            apps, "close", return_value=closed
        ) as close, mock.patch.object(apps, "notify"), mock.patch.object(cli.os, "execvp") as execvp:
            result = cli.main(["open", *argv])
        return result, close, execvp

    def test_not_elsewhere_just_starts(self):
        _, close, execvp = self.run_open(["chrome", "--", "/usr/bin/google-chrome-stable", "x"], [])
        close.assert_not_called()
        execvp.assert_called_once_with("/usr/bin/google-chrome-stable", ["/usr/bin/google-chrome-stable", "x"])

    def test_moves_and_restores_tabs(self):
        _, close, execvp = self.run_open(["chrome"], [Process(100, 1, "chrome", THERE)])
        close.assert_called_once()
        execvp.assert_called_once_with(
            "google-chrome-stable", ["google-chrome-stable", "--restore-last-session"]
        )

    def test_does_not_start_while_still_closing(self):
        result, _, execvp = self.run_open(["chrome"], [Process(100, 1, "chrome", THERE)], closed=False)
        self.assertEqual(result, 1)
        execvp.assert_not_called()


class LauncherTest(unittest.TestCase):
    def test_override_text(self):
        text = apps.override_text(DESKTOP_FILE, CHROME)
        self.assertIn("[Desktop Entry]\nX-Desktop-Switcher=chrome\n", text)
        self.assertIn("Exec=desktop-switcher open chrome -- /usr/bin/google-chrome-stable %U\n", text)
        self.assertIn("Exec=desktop-switcher open chrome -- /usr/bin/google-chrome-stable --new-window\n", text)
        self.assertNotIn("DBusActivatable", text)
        self.assertEqual(text.count(apps.MARKER), 1)

    def test_setup_and_remove(self):
        with tempfile.TemporaryDirectory() as tmp:
            system = Path(tmp) / "system" / "applications"
            system.mkdir(parents=True)
            (system / CHROME.desktop_file).write_text(DESKTOP_FILE)
            env = {"XDG_DATA_DIRS": str(system.parent), "XDG_DATA_HOME": str(Path(tmp) / "home")}
            with mock.patch.dict(os.environ, env):
                self.assertIn("set up", apps.setup_launcher(CHROME))
                self.assertTrue(apps.is_ours(apps.user_launcher(CHROME)))
                self.assertIn("set up", apps.setup_launcher(CHROME))  # running it again is fine
                self.assertIn("not installed", apps.setup_launcher(apps.APPS["steam"]))
                self.assertIn("restored", apps.remove_launcher(CHROME))
                self.assertFalse(apps.user_launcher(CHROME).exists())

    def test_own_launcher_left_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            system = Path(tmp) / "system" / "applications"
            system.mkdir(parents=True)
            (system / CHROME.desktop_file).write_text(DESKTOP_FILE)
            own = Path(tmp) / "home" / "applications" / CHROME.desktop_file
            own.parent.mkdir(parents=True)
            own.write_text("[Desktop Entry]\nExec=my-chrome\n")
            env = {"XDG_DATA_DIRS": str(system.parent), "XDG_DATA_HOME": str(Path(tmp) / "home")}
            with mock.patch.dict(os.environ, env):
                self.assertIn("left alone", apps.setup_launcher(CHROME))
                self.assertIsNone(apps.remove_launcher(CHROME))
            self.assertEqual(own.read_text(), "[Desktop Entry]\nExec=my-chrome\n")


class CloseTest(unittest.TestCase):
    def test_terminates_and_waits(self):
        import subprocess

        child = subprocess.Popen(["sleep", "30"])
        app = apps.App("x", "X", frozenset({"sleep"}), ("sleep",), "x.desktop", quit_timeout=5)
        # Reap the child as soon as it exits so it does not linger as a zombie.
        with mock.patch.object(apps, "_alive", lambda pid: child.poll() is None):
            self.assertTrue(apps.close(app, [Process(child.pid, os.getpid(), "/usr/bin/sleep")]))


class CustomAppTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        system = self.root / "system" / "applications"
        system.mkdir(parents=True)
        (system / "spotify-launcher.desktop").write_text(
            "[Desktop Entry]\nName=Spotify (Launcher)\nExec=env LANG=C spotify-launcher %U\nStartupWMClass=Spotify\n"
            "[Desktop Action x]\nName=Other\nExec=other\n"
        )
        (system / "com.example.Flat.desktop").write_text("[Desktop Entry]\nName=Flat\nExec=/usr/bin/flatpak run x\n")
        env = {
            "XDG_DATA_DIRS": str(system.parent),
            "XDG_DATA_HOME": str(self.root / "home"),
            "XDG_CONFIG_HOME": str(self.root / "cfg"),
        }
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_add_by_menu_name(self):
        with mock.patch.object(apps.shutil, "which", return_value=None):
            app = apps.add_custom("spotify")
        self.assertEqual(app.id, "spotify-launcher")
        self.assertEqual(app.name, "Spotify (Launcher)")
        self.assertEqual(app.command, ("spotify-launcher",))
        self.assertEqual(app.exe_names, frozenset({"spotify-launcher", "Spotify", "spotify"}))
        self.assertIn("spotify-launcher", apps.all_apps())

    def test_process_follows_symlink(self):
        with mock.patch.object(apps.shutil, "which", return_value="/usr/bin/spotify-launcher"), mock.patch.object(
            apps.os.path, "realpath", return_value="/opt/spotify/spotify"
        ):
            self.assertEqual(apps.add_custom("Spotify").exe_names, frozenset({"spotify", "Spotify"}))

    def test_process_override(self):
        self.assertEqual(apps.add_custom("spotify-launcher.desktop", "Spotify").exe_names, frozenset({"Spotify"}))

    def test_exact_name_and_ambiguity(self):
        system = Path(os.environ["XDG_DATA_DIRS"]) / "applications"
        (system / "spotify-tui.desktop").write_text("[Desktop Entry]\nName=Spotify TUI\nExec=spt\n")
        with self.assertRaises(apps.AddError) as err:
            apps.add_custom("spotify")
        self.assertIn("More than one", str(err.exception))
        self.assertEqual(apps.add_custom("Spotify TUI").id, "spotify-tui")
        self.assertEqual(apps.add_custom("spotify-launcher").id, "spotify-launcher")

    def test_refusals(self):
        for query in ("nothing", "Flat", "discord"):
            with self.assertRaises(apps.AddError):
                apps.add_custom(query)

    def test_forget(self):
        apps.add_custom("Spotify", "spotify")
        self.assertEqual(apps.forget_custom("spotify-launcher").name, "Spotify (Launcher)")
        self.assertNotIn("spotify-launcher", apps.all_apps())
        self.assertIsNone(apps.forget_custom("spotify-launcher"))

    def test_add_command_sets_up_launcher(self):
        with mock.patch("sys.stdout"):
            cli.main(["apps", "add", "Spotify", "--process", "spotify"])
        launcher = self.root / "home" / "applications" / "spotify-launcher.desktop"
        self.assertIn("Exec=desktop-switcher open spotify-launcher -- env LANG=C spotify-launcher %U", launcher.read_text())
        with mock.patch("sys.stdout"):
            cli.main(["apps", "forget", "spotify-launcher"])
        self.assertFalse(launcher.exists())


class UserProcessesTest(unittest.TestCase):
    def test_reads_own_process(self):
        me = next(p for p in apps.user_processes() if p.pid == os.getpid())
        self.assertEqual(me.ppid, os.getppid())
        self.assertEqual(me.env.get("PATH"), os.environ.get("PATH"))


if __name__ == "__main__":
    unittest.main()
