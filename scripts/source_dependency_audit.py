#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Fail-closed source dependency inventory, NOT a third-party legal clearance.

Checks checked-in AudioHub Python/JS/CSS/HTML for new unreviewed runtime
dependencies and remote executable assets. Does NOT prove originality or
read upstream/binary rootfs licenses. The human review remains mandatory.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import re
import sys

KNOWN_RUNTIME_IMPORTS = {"dbus", "gi"}  # python3-dbus, python3-gi on actual Pi
KNOWN_REPO_ASSETS = {"app.js", "styles.css"}
SCHEMA = "rivanox-audiohub-source-dependency-observation/1"
SPDX = re.compile(r"(?m)^# SPDX-License-Identifier: AGPL-3\.0-only\s*$")
JS_SPDX = re.compile(r"(?m)^// SPDX-License-Identifier: AGPL-3\.0-only\s*$")
HTTP_EXEC = re.compile(
    r"<script\b[^>]*\bsrc\s*=\s*['\"]https?://|"
    r"<link\b[^>]*\b(?:href)\s*=\s*['\"]https?://[^'\"]+\.(?:js|css)|"
    r"@import\s+(?:url\()?['\"]?https?://",
    re.IGNORECASE,
)
JS_EXTERNAL = re.compile(
    r"\b(?:import\s*\(|fetch\s*\(|new\s+WebSocket\s*\()\s*['\"]https?://",
    re.IGNORECASE,
)


def inspect(root: Path) -> dict:
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Source root missing")
    source = root / "src/audiohub"
    web = root / "web"
    if source.is_symlink() or not source.is_dir() or web.is_symlink() or not web.is_dir():
        raise ValueError("Expected AudioHub source and UI are missing")
    source_files = sorted(source.glob("*.py"))
    if len(source_files) < 10 or any(p.is_symlink() for p in source_files):
        raise ValueError("Missing, suspicious or symlinked AudioHub Python source")
    third_party_imports = set()
    for path in source_files:
        payload = path.read_text(encoding="utf-8")
        if path.name != "__init__.py" and not SPDX.search(payload):
            raise ValueError("Missing reviewable SPDX header on " + path.name)
        try:
            tree = ast.parse(payload, filename=path.name)
        except SyntaxError as exc:
            raise ValueError("Python source parse failed") from exc
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                packages = [alias.name.split(".", 1)[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                packages = [node.module.split(".", 1)[0]]
            else:
                continue
            for package in packages:
                if package in sys.stdlib_module_names or package == "__future__":
                    continue
                if package not in KNOWN_RUNTIME_IMPORTS:
                    raise ValueError("Unreviewed external runtime import: " + package)
                third_party_imports.add(package)
    if not third_party_imports:
        raise ValueError("External D-Bus/GObject runtime usage unexpectedly absent")
    js = web / "app.js"
    css = web / "styles.css"
    html = web / "index.html"
    if any(p.is_symlink() or not p.is_file() for p in (js, css, html)):
        raise ValueError("Missing or symlinked web asset")
    script = js.read_text(encoding="utf-8")
    if not JS_SPDX.search(script):
        raise ValueError("Web script SPDX header missing")
    if HTTP_EXEC.search(css.read_text(encoding="utf-8")) or HTTP_EXEC.search(html.read_text(encoding="utf-8")):
        raise ValueError("Unreviewed remote executable CSS/JS asset")
    if JS_EXTERNAL.search(script):
        raise ValueError("Unreviewed external network executable dependency")
    if not ("./app.js" in html.read_text(encoding="utf-8")
            and "./styles.css" in html.read_text(encoding="utf-8")):
        raise ValueError("Web assets cannot be proven local")
    return {
        "schema": SCHEMA,
        "python_production_files_inspected": len(source_files),
        "third_party_runtime_imports": sorted(third_party_imports),
        "web_javascript_and_css_external_execution_detected": False,
        "manual_code_origin_review_complete": False,
        "third_party_image_license_review_complete": False,
        "model_c_relicense_approved": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    try:
        evidence = inspect(args.root)
    except (OSError, ValueError, UnicodeError) as exc:
        parser.exit(2, "Third-party source observation REFUSED: " + str(exc) + "\n")
    print(json.dumps(evidence, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
