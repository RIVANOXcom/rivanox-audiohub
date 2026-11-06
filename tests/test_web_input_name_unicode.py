"""Exercise the real shipping preview input-name validator in Node.js.

No device API, browser automation, network, third-party packages or hardware.
"""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / "web" / "app.js"


def validator_source():
    source = PREVIEW.read_text(encoding="utf-8")
    start = source.index("  const validName = raw => {")
    end = source.index("\n  };", start) + len("\n  };")
    return source[start:end]


class BrowserNameUnicodeTests(unittest.TestCase):
    def test_preview_uses_real_unicode_property_escape(self):
        text = validator_source()
        self.assertIn(r"/[\p{C}<>]/u.test(name)", text)
        self.assertNotIn(r"/[\\p{C}<>]/u.test(name)", text)
        self.assertIn("Array.from(name).length > 32", text)

    @unittest.skipUnless(shutil.which("node"), "Node.js runtime unavailable")
    def test_real_shipped_javascript_validator(self):
        cases = r'''
const assert = require("node:assert/strict");
for (const value of ["Laptop", "PC Audio", "Computer", "p", "C", "C++",
                     "Musica", "Música", "Straße", "🙂"]) {
  assert.equal(validName(value), value, "normal label rejected: " + value);
}
assert.equal(validName("  Laptop  "), "Laptop");
for (const value of ["A\u0000B", "A\u0001B", "A\u007fB", "A\u202eB",
                     "A\u200dB", "A<B", "A>B", "X".repeat(33), "  "]) {
  assert.equal(validName(value), null, "unsafe label accepted: " + JSON.stringify(value));
}
assert.equal(validName("🙂".repeat(32)), "🙂".repeat(32));
assert.equal(validName("🙂".repeat(33)), null);
assert.equal(validName(3), null);
'''
        result = subprocess.run(
            ["node", "-e", validator_source() + "\n" + cases],
            capture_output=True, text=True, timeout=15, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
