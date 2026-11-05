"""Static checks for headless integration and non-releasable preview safeguards."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RuntimeStaticTests(unittest.TestCase):
    def test_no_published_shared_wifi_password(self):
        for file in (ROOT / "src").rglob("*.py"):
            self.assertNotIn("AudioHub-Setup-2026", file.read_text())
        self.assertNotIn("AudioHub-Setup-2026", (ROOT / "build-image.sh").read_text())

    def test_image_has_disabled_ssh_and_random_local_password(self):
        script = (ROOT / "build-image.sh").read_text()
        self.assertIn("ENABLE_SSH=0", script)
        self.assertIn("openssl rand -hex 32", script)
        self.assertIn("AUDIOHUB_BUILD_ACCEPT_PREVIEW", script)

    def test_runtime_is_user_service(self):
        service = (ROOT / "image/stage-audiohub/01-install/files/systemd/audiohub-runtime.service").read_text()
        self.assertIn("python3 -m audiohub.runtime", service)
        self.assertIn("NoNewPrivileges=yes", service)

    def test_runtime_child_processes_are_stopped_by_systemd_cgroup(self):
        service = (
            ROOT / "image/stage-audiohub/01-install/files/systemd/audiohub-runtime.service"
        ).read_text()
        self.assertIn("KillMode=control-group", service)
        self.assertIn("Restart=always", service)
        source = (ROOT / "src/audiohub/runtime.py").read_text()
        self.assertIn("def _stop_all_managed_routes(self):", source)
        self.assertIn("def poll_safely(self):", source)



if __name__ == "__main__":
    unittest.main()
