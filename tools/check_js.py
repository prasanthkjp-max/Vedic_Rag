#!/usr/bin/env python3
"""Syntax-check the inline <script> blocks in static/index.html via `node --check`.

No bundler/build step exists, so this is the cheap guard that a frontend edit
didn't introduce a JS syntax error. Exit 0 if all inline scripts parse, else 1.
Requires `node` on PATH.
"""
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(ROOT, "static", "index.html")


def main():
    src = open(INDEX, encoding="utf-8").read()
    scripts = re.findall(r"<script(?![^>]*src)[^>]*>(.*?)</script>", src, re.S)
    if not scripts:
        print("No inline scripts found.")
        return 0
    failed = 0
    for i, s in enumerate(scripts):
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
            f.write(s)
            path = f.name
        try:
            r = subprocess.run(["node", "--check", path], capture_output=True, text=True)
        finally:
            os.unlink(path)
        if r.returncode != 0:
            failed += 1
            print(f"inline script {i} FAILED node --check:\n{r.stderr[:1000]}")
        else:
            print(f"inline script {i}: OK")
    print("frontend JS OK" if failed == 0 else f"{failed} script(s) failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
