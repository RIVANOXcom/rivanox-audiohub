# SPDX-License-Identifier: AGPL-3.0-only
"""Native Pi4 operator music entrypoint: local-only, staged and fail-closed."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "image/stage-audiohub/01-install/files/bin/audiohub-music"
STAGE = ROOT / "image/stage-audiohub/01-install/00-run.sh"
AUDIT = ROOT / "image/stage-audiohub/02-audit/00-run.sh"


class MusicLauncherTests(unittest.TestCase):
    def shell(self, *args):
        return subprocess.run(["/bin/sh", str(LAUNCHER), *args],
                              capture_output=True, text=True, timeout=5,
                              check=False)

    def test_launcher_shell_is_valid_and_has_a_single_privately_bounded_entry(self):
        check = subprocess.run(["/bin/sh", "-n", str(LAUNCHER)],
                               capture_output=True, text=True, timeout=5)
        self.assertEqual(check.returncode, 0, check.stderr)
        text = LAUNCHER.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("#!/bin/sh\n"))
        self.assertIn("# SPDX-License-Identifier: AGPL-3.0-only", text)
        self.assertIn("set -eu", text)
        self.assertIn("PYTHONPATH=/opt/audiohub/src", text)
        self.assertIn("exec /usr/bin/python3 -m audiohub.local_music", text)
        self.assertIn('--guided --library "$folder" --minutes "$minutes" --level "$level"', text)
        self.assertNotIn("eval ", text)
        self.assertNotIn("sudo ", text)
        self.assertNotIn("systemctl ", text)
        self.assertNotIn("curl ", text)
        self.assertNotIn("wget ", text)
        self.assertNotIn(" --play", text)

    def test_help_is_available_without_python_or_rootfs(self):
        for arg in ("--help", "-h"):
            with self.subTest(arg=arg):
                result = self.shell(arg)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("audiohub-music", result.stdout)
                self.assertIn("PLAY", result.stdout)
                self.assertIn("SHUFFLE", result.stdout)
                self.assertIn("q=stop", result.stdout)
                self.assertEqual(result.stderr, "")

    def test_reject_extra_arguments_before_any_playback(self):
        for args in (("--play", "--guided"), ("--library", "/tmp"),
                     ("/tmp/private", "--minutes"), ("x", "y")):
            with self.subTest(args=args):
                result = self.shell(*args)
                self.assertEqual(result.returncode, 2)
                self.assertTrue(result.stderr.strip())
                self.assertNotIn("Playing track", result.stdout)

    def test_relative_or_option_like_folder_is_rejected(self):
        for folder in ("relative/music", "../private", "--play", "-x", "."):
            with self.subTest(folder=folder):
                result = self.shell(folder)
                self.assertEqual(result.returncode, 2)
                self.assertIn("Invalid option or relative folder", result.stderr)
                self.assertNotIn("Playing track", result.stdout)

    def test_help_shows_quiet_levels_time_and_readonly_list(self):
        text = self.shell("--help").stdout
        for name in ("--level quiet|soft|normal", "--minutes 1..30",
                     "--list", "--show-titles", "0.05", "0.10",
                     "0.20", "PLAY", "not calibrated speaker loudness"):
            with self.subTest(name=name):
                self.assertIn(name, text)

    def test_launcher_refuses_unsafe_levels_minutes_and_duplicate_flags(self):
        bad = [
            ("--level", "loud"), ("--level", "0.95"),
            ("--level", "--play"), ("--level", "quiet", "--level", "soft"),
            ("--minutes", "0"), ("--minutes", "31"), ("--minutes", "10.0"),
            ("--minutes", "+2"), ("--minutes", "00001"),
            ("--minutes", "999999999999999999999999999"),
            ("--minutes", "10", "--minutes", "5"),
            ("--minutes", "--play"), ("--minutes",),
            ("--show-titles", "--show-titles"), ("--list", "--list"),
            ("/tmp/one", "/tmp/two"),
            ("--play", "/tmp"), ("--guided", "/tmp"),
            ("--library", "/tmp"), ("--help", "--play")
        ]
        for args in bad:
            with self.subTest(args=args):
                result = self.shell(*args)
                self.assertEqual(result.returncode, 2, (args, result.stderr))
                self.assertTrue(result.stderr.strip())
                self.assertNotIn("Playing track", result.stdout)

    def test_launcher_argument_contract_has_no_autoplay_or_global_mixer_changes(self):
        text = LAUNCHER.read_text(encoding="utf-8")
        self.assertIn("if [ \"$list_only\" -eq 1 ]; then", text)
        self.assertIn('--library "$folder" --show-titles', text)
        self.assertIn('--guided --library "$folder" --minutes "$minutes" --level "$level"', text)
        for token in ("--play", "pw-cat", "pw-metadata", "pw-link",
                      "systemctl restart", "sudo", "eval ", "curl ", "wget "):
            with self.subTest(token=token):
                self.assertNotIn(token, text)
        self.assertIn("PLAY is a separate explicit TTY input", text)

    def test_builder_installs_real_command_and_prepares_private_folder(self):
        script = STAGE.read_text(encoding="utf-8")
        self.assertIn('install -m755 files/bin/audiohub-music', script)
        self.assertIn('"${ROOTFS_DIR}/usr/local/bin/audiohub-music"', script)
        self.assertIn("install -d -o audiohub -g audiohub -m700 /home/audiohub/PrivateMusic", script)
        self.assertIn("runuser -u audiohub -- /usr/local/bin/audiohub-music --help", script)
        self.assertNotIn("systemctl enable audiohub-music", script)

    def test_native_rootfs_audit_checks_installed_command_and_directory(self):
        script = AUDIT.read_text(encoding="utf-8")
        self.assertIn('test -x "${ROOTFS_DIR}/usr/local/bin/audiohub-music"', script)
        self.assertIn('test -d "${ROOTFS_DIR}/home/audiohub/PrivateMusic"', script)
        self.assertIn("stat -c '%a'", script)
        self.assertIn("= 755", script)
        self.assertIn("= 700", script)
        self.assertNotIn("public_release_ready=true", script)

    def test_pin_existing_release_pipeline_and_no_implicit_autoplay(self):
        builder = (ROOT / "build-image.sh").read_text(encoding="utf-8")
        self.assertIn('cp -a "$ROOT/image/stage-audiohub"', builder)
        self.assertIn("AUDIOHUB_BUILD_ACCEPT_PREVIEW", builder)
        src = (ROOT / "src/audiohub/local_music.py").read_text(encoding="utf-8")
        self.assertIn("music_library.guided_session(", src)
        self.assertIn("--guided", src)
        gate = (ROOT / "src/audiohub/music_library.py").read_text(encoding="utf-8")
        self.assertIn('if type(answer) is not str or answer != "PLAY":', gate)


if __name__ == "__main__":
    unittest.main()
