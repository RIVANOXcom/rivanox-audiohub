"""Run JavaScript locale behavior tests as part of the standard Python source suite."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BrowserLocaleRuntimeTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_locale_switch_races_fallback_and_accessibility(self):
        result = subprocess.run(
            ["node", str(ROOT / "tests" / "locale_runtime.test.cjs")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("3 scenarios passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
