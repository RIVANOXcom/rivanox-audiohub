"""Static guard for non-interactive, least-privilege appliance account."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class NonInteractiveAccountTests(unittest.TestCase):
    def test_user_is_locked_only_after_eq_generation(self):
        installer = (ROOT / "image/stage-audiohub/01-install/00-run.sh").read_text()
        initialize = "runuser -u audiohub -- python3 -m audiohub.eq_setup"
        lock = "passwd -l audiohub"
        privilege = "gpasswd -d audiohub sudo"
        self.assertIn(initialize, installer)
        self.assertIn(lock, installer)
        self.assertIn(privilege, installer)
        self.assertLess(installer.index(initialize), installer.index(lock))
        self.assertLess(installer.index(lock), installer.index(privilege))

    def test_public_image_has_ssh_disabled(self):
        builder = (ROOT / "build-image.sh").read_text()
        self.assertIn("ENABLE_SSH=0", builder)
        self.assertIn("openssl rand -hex 32", builder)


if __name__ == "__main__":
    unittest.main()
