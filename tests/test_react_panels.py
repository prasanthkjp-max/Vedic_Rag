"""React advanced-panel regression test.

The TypeScript types in frontend/src/types/astrology.ts are hand-written, so
`tsc` cannot notice when the engine's real output differs from them. This test
renders every panel (server-side, no browser) against real
`get_astrological_chart` output for every calculation system, plus light-mode
charts whose advanced sections are empty `{}`, and fails on any render crash or
any "undefined"/"NaN" in the markup.

Needs Node + `npm ci` in frontend/ (CI does this). Set FRONTEND_DIR to use a
different install (e.g. one built for this OS). Exit 0 = pass, 1 = fail,
and a clear SKIP (exit 0) only when Node itself is unavailable locally.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

FRONTEND = os.environ.get("FRONTEND_DIR") or os.path.join(ROOT, "frontend")
BIN = os.path.join(FRONTEND, "node_modules", ".bin", "esbuild")

if not shutil.which("node"):
    if os.environ.get("CI"):
        print("FAIL: node is required in CI")
        sys.exit(1)
    print("SKIP: node not installed")
    sys.exit(0)
if not os.path.exists(BIN):
    print(f"FAIL: {BIN} missing — run `npm ci` in frontend/ first")
    sys.exit(1)

from src.engines import astro_engine as ae  # noqa: E402

# (calc_type, dasa_system, ayanamsa, dob parts) — covers every selector option.
CASES = {
    "parashara":  ("Parashara", "Vimshottari", "Lahiri"),
    "thiru":      ("Thirukanitha", "Vimshottari", "Lahiri"),
    "kp":         ("KP", "Vimshottari", "KP"),
    "jaimini":    ("Jaimini", "Chara", "Lahiri"),
    "nadi":       ("Nadi", "Vimshottari", "Raman"),
    "vakya":      ("Vakya", "Ashtottari", "Lahiri"),
    "ashtottari": ("Parashara", "Ashtottari", "Yukteshwar"),
    "tropical":   ("Parashara", "Vimshottari", "Tropical"),
}

work = tempfile.mkdtemp(prefix="react_panels_")
try:
    for name, (ct, ds, ay) in CASES.items():
        chart = ae.get_astrological_chart(1990, 3, 10, 8, 30, 80.27, 13.08, ay, 5.5, "male", False, ct, ds)
        with open(os.path.join(work, f"chart_{name}.json"), "w") as fh:
            json.dump(chart, fh, default=str)
    light = ae.get_astrological_chart(1990, 3, 10, 8, 30, 80.27, 13.08, "Lahiri", 5.5, "male", True)
    with open(os.path.join(work, "chart_light.json"), "w") as fh:
        json.dump(light, fh, default=str)

    bundle = os.path.join(work, "render.cjs")
    build = subprocess.run(
        [BIN, os.path.join(FRONTEND, "tests", "render-panels.tsx"), "--bundle", "--platform=node",
         "--format=cjs", f"--outfile={bundle}", "--loader:.css=empty", "--jsx=automatic",
         "--define:window=globalThis", "--log-level=error"],
        cwd=FRONTEND, capture_output=True, text=True)
    if build.returncode != 0:
        print("FAIL: could not bundle the render harness\n" + build.stdout + build.stderr)
        sys.exit(1)

    run = subprocess.run(["node", bundle, work], capture_output=True, text=True, cwd=FRONTEND)
    out = run.stdout.strip()
    print(out)
    if run.returncode != 0:
        print(run.stderr[-2000:])
        print("\nFAILED")
        sys.exit(1)
    print(f"\nAll React panels render cleanly against real engine output "
          f"({len(CASES) + 1} charts x 5 panels).")
finally:
    shutil.rmtree(work, ignore_errors=True)
