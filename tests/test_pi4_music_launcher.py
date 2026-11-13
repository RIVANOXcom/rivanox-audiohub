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

    def test_readiness_help_and_native_wrapper_forwarding(self):
        help_text = self.shell("--help").stdout
        self.assertIn("--check", help_text)
        self.assertIn("without sound", help_text)
        source = LAUNCHER.read_text(encoding="utf-8")
        self.assertIn("check_only=0", source)
        self.assertIn('exec /usr/bin/python3 -m audiohub.local_music --check --library "$folder"', source)
        self.assertIn('if [ "$check_only" -eq 1 ]; then', source)
        self.assertIn("No default-output", (ROOT / "src/audiohub/local_music.py").read_text())
        self.assertNotIn(" --play", source)
        self.assertNotIn("pw-cat", source)

    def test_readiness_conflicting_options_rejected_before_python_or_audio(self):
        for args in (
            ("--check", "--list"),
            ("--check", "--show-titles"),
            ("--check", "--minutes", "10"),
            ("--check", "--level", "quiet"),
            ("--check", "--check"),
            ("/home/audiohub/PrivateMusic", "--list", "--check"),
            ("/home/audiohub/PrivateMusic", "--check", "--show-titles"),
            ("--check", "/home/audiohub/PrivateMusic", "--level", "normal"),
        ):
            with self.subTest(args=args):
                output = self.shell(*args)
                self.assertEqual(output.returncode, 2, output.stderr)
                self.assertNotIn("Playing track", output.stdout)
                self.assertNotIn("PLAY confirmed", output.stdout)
                self.assertTrue(output.stderr.strip())

    def test_first_sound_preflight_help_and_native_chroot(self):
        help_text = self.shell("--help").stdout
        self.assertIn("audiohub-music --speaker-check", help_text)
        self.assertIn("FIRST SOUND without a WAV library", help_text)
        launcher = LAUNCHER.read_text(encoding="utf-8")
        self.assertIn('if [ "$#" -ge 1 ] && [ "$1" = "--speaker-check" ]; then', launcher)
        self.assertIn('exec /usr/bin/python3 -m audiohub.local_music --speaker-check', launcher)
        for args in (("--speaker-check", "--speaker-check"),
                     ("--speaker-check", "--speaker-guide"),
                     ("--speaker-check", "--speaker-test"),
                     ("--speaker-check", "--check"),
                     ("--speaker-check", "--level", "quiet"),
                     ("--speaker-check", "/home/audiohub/PrivateMusic"),
                     ("/home/audiohub/PrivateMusic", "--speaker-check")):
            with self.subTest(args=args):
                result = self.shell(*args)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertNotIn("Playing track", result.stdout)
        self.assertNotIn("pw-cat", launcher)
        self.assertNotIn("sudo ", launcher)
        native = STAGE.read_text(encoding="utf-8")
        self.assertIn("first_sound_check_output=", native)
        self.assertIn("/usr/local/bin/audiohub-music --speaker-check", native)
        self.assertIn("no WAV files needed.", native)
        self.assertIn("Read-only only: NO sound", native)

    def test_native_chroot_smokes_installed_nonplaying_readiness(self):
        stage = STAGE.read_text(encoding="utf-8")
        self.assertIn("empty_check_output=", stage)
        self.assertIn("/usr/local/bin/audiohub-music --check", stage)
        self.assertIn('test "$empty_check_status" -eq 2', stage)
        self.assertIn('WAV library: NEEDS ATTENTION', stage)
        self.assertIn('Local PipeWire playback tool:', stage)
        self.assertIn("No playback, global mixer/route change", stage)

    def test_stereo_help_explains_mono_refusal_and_unboosted_channel(self):
        text = self.shell("--help").stdout
        for token in ("--channel both|left|right", "silences only",
                      "opposite stereo WAV channel", "mono needs both",
                      "PLAY is required"):
            with self.subTest(token=token):
                self.assertIn(token, text)

    def test_stereo_invalid_modes_and_conflicting_nonplaying_flags_fail_closed(self):
        for args in (
            ("--channel",), ("--channel", "center"),
            ("--channel", "LEFT"), ("--channel", "1"),
            ("--channel", "left", "--channel", "right"),
            ("--channel", "--play"), ("--channel", "left", "--list"),
            ("--list", "--channel", "both"),
            ("--channel", "left", "--check"),
            ("--check", "--channel", "right"),
            ("--channel", "both", "--check"),
        ):
            with self.subTest(args=args):
                r = self.shell(*args)
                self.assertEqual(r.returncode, 2, r.stderr)
                self.assertNotIn("Playing track", r.stdout)
                self.assertTrue(r.stderr.strip())

    def test_stereo_mode_passes_only_into_guided_confirmed_player(self):
        text = LAUNCHER.read_text(encoding="utf-8")
        self.assertIn("channel=both", text)
        self.assertIn('both|left|right) channel=$2', text)
        self.assertIn('--level "$level" --channel "$channel"', text)
        self.assertIn('if [ "$channel_seen" -ne 0 ]; then', text)
        self.assertNotIn(" --play", text)
        self.assertNotIn("pw-cat", text)
        self.assertNotIn("sudo ", text)

    def test_native_script_checks_installed_invalid_channel_before_audio(self):
        script = STAGE.read_text(encoding="utf-8")
        self.assertIn("invalid_channel_output=", script)
        self.assertIn("/usr/local/bin/audiohub-music --channel center", script)
        self.assertIn('test "$invalid_channel_status" -eq 2', script)
        self.assertIn("Only both, left or right stereo", script)

    def test_builtin_original_speaker_sample_has_exclusive_operator_entry(self):
        output = self.shell("--help")
        self.assertEqual(output.returncode, 0, output.stderr)
        for phrase in ("audiohub-music --speaker-test", "original 2.1s",
                       "No WAV required", "separate PLAY", "quiet stream"):
            self.assertIn(phrase, output.stdout)
        text = LAUNCHER.read_text(encoding="utf-8")
        self.assertIn('if [ "$#" -ge 1 ] && [ "$1" = "--speaker-test" ]; then', text)
        self.assertIn('exec /usr/bin/python3 -m audiohub.local_music --speaker-test', text)
        self.assertNotIn("pw-cat", text)
        self.assertNotIn(" --play", text)
        self.assertNotIn("sudo ", text)
        self.assertNotIn("eval ", text)

    def test_builtin_speaker_test_rejects_all_other_options_before_python(self):
        for args in (
            ("--speaker-test", "--speaker-test"),
            ("--speaker-test", "--level", "quiet"),
            ("--speaker-test", "--minutes", "5"),
            ("--speaker-test", "--channel", "left"),
            ("--speaker-test", "--list"),
            ("--speaker-test", "--check"),
            ("--speaker-test", "--show-titles"),
            ("--speaker-test", "/home/audiohub/PrivateMusic"),
            ("/home/audiohub/PrivateMusic", "--speaker-test"),
            ("--check", "--speaker-test"),
        ):
            with self.subTest(args=args):
                output = self.shell(*args)
                self.assertEqual(output.returncode, 2, output.stderr)
                self.assertTrue(output.stderr.strip())
                self.assertNotIn("PLAY confirmed", output.stdout)

    def test_repeated_speaker_side_help_and_exclusive_allowlist(self):
        help_text = self.shell("--help").stdout
        self.assertIn("--speaker-test [left|right|both]", help_text)
        self.assertIn("replays that channel 3 times", help_text)
        source = LAUNCHER.read_text(encoding="utf-8")
        self.assertIn('left|right|both) ;;', source)
        self.assertIn('--speaker-test "$2"', source)
        self.assertIn('if [ "$#" -gt 2 ]; then', source)
        self.assertNotIn("pw-cat", source)
        self.assertNotIn(" --play", source)
        self.assertNotIn("eval ", source)
        self.assertNotIn("sudo ", source)

    def test_repeated_speaker_rejects_unsupported_side_or_extra_options(self):
        for args in (
            ("--speaker-test", "sequence"),
            ("--speaker-test", "mono"),
            ("--speaker-test", "LEFT"),
            ("--speaker-test", "center"),
            ("--speaker-test", "left", "right"),
            ("--speaker-test", "left", "--check"),
            ("--speaker-test", "right", "--minutes", "30"),
            ("--speaker-test", "both", "--level", "normal"),
            ("--speaker-test", "left", "--play"),
            ("--speaker-test", "--channel", "left"),
        ):
            with self.subTest(args=args):
                result = self.shell(*args)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertTrue(result.stderr.strip())
                self.assertNotIn("PLAY confirmed", result.stdout)

    def test_native_chroot_repeated_side_reaches_python_tty_gate(self):
        native = STAGE.read_text(encoding="utf-8")
        self.assertIn("speaker_side_noninteractive_output=", native)
        self.assertIn("/usr/local/bin/audiohub-music --speaker-test left", native)
        self.assertIn('test "$speaker_side_noninteractive_status" -eq 2', native)
        self.assertIn("Local player unavailable or stopped", native)

    def test_native_chroot_refuses_nonterminal_speaker_test_no_audio(self):
        text = STAGE.read_text(encoding="utf-8")
        self.assertIn("speaker_noninteractive_output=", text)
        self.assertIn("/usr/local/bin/audiohub-music --speaker-test", text)
        self.assertIn('test "$speaker_noninteractive_status" -eq 2', text)
        self.assertIn("Local player unavailable or stopped", text)

    def test_guided_speaker_command_is_exclusive_and_safe_in_launcher(self):
        help_text = self.shell("--help").stdout
        self.assertIn("audiohub-music --speaker-guide [left|right|both]", help_text)
        self.assertIn("targeted left/right/both side", help_text)
        self.assertIn("FIRST checks private sink and pw-cat", help_text)
        self.assertIn("refuses all PLAY unless both", help_text)
        self.assertIn("LOCAL physical observations", help_text)
        self.assertIn("RETRY same side once", help_text)
        self.assertIn("no auto-next", help_text)
        shell = LAUNCHER.read_text(encoding="utf-8")
        self.assertIn('if [ "$#" -ge 1 ] && [ "$1" = "--speaker-guide" ]; then', shell)
        self.assertIn('exec /usr/bin/python3 -m audiohub.local_music --speaker-guide', shell)
        self.assertIn('exec /usr/bin/python3 -m audiohub.local_music --speaker-guide "$2"', shell)
        self.assertIn("left|right|both) ;;", shell)
        for args in (("--speaker-guide", "--speaker-guide"),
                     ("--speaker-guide", "--speaker-test"),
                     ("--speaker-guide", "--level", "quiet"),
                     ("--speaker-guide", "--check"),
                     ("--speaker-guide", "RIGHT"),
                     ("--speaker-guide", "sequence"),
                     ("--speaker-guide", "left", "--play"),
                     ("--speaker-guide", "both", "--speaker-check"),
                     ("--speaker-guide", "/home/audiohub/PrivateMusic"),
                     ("/home/audiohub/PrivateMusic", "--speaker-guide")):
            with self.subTest(args=args):
                result = self.shell(*args)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertNotIn("Playing track", result.stdout)
        self.assertNotIn("pw-cat", shell)
        self.assertNotIn("sudo ", shell)
        self.assertNotIn("eval ", shell)

    def test_native_chroot_guided_speaker_never_starts_without_tty(self):
        native = STAGE.read_text(encoding="utf-8")
        self.assertIn("speaker_guide_noninteractive_output=", native)
        self.assertIn("/usr/local/bin/audiohub-music --speaker-guide", native)
        self.assertIn('test "$speaker_guide_noninteractive_status" -eq 2', native)
        self.assertIn("Local player unavailable or stopped", native)

    def test_native_targeted_guide_refuses_unattended_chroot(self):
        native = STAGE.read_text(encoding="utf-8")
        self.assertIn("targeted_guide_noninteractive_output=", native)
        self.assertIn("/usr/local/bin/audiohub-music --speaker-guide right", native)
        self.assertIn('test "$targeted_guide_noninteractive_status" -eq 2', native)
        self.assertIn("Local player unavailable or stopped", native)

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
