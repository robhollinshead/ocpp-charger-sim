#!/usr/bin/env python3
"""Run pytest and write a timestamped markdown report to testing/reports/."""
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPORTS_DIR = Path(__file__).resolve().parent.parent.parent / "testing" / "reports"


def main() -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    backend_dir = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short", "-m", "not slow"],
        cwd=backend_dir,
        capture_output=True,
        text=True,
    )
    out = result.stdout + result.stderr

    # Parse summary: "22 passed in 0.37s" or "20 passed, 2 failed in 1.23s"
    passed = failed = skipped = 0
    for m in re.finditer(r"(\d+) passed", out):
        passed = int(m.group(1))
    for m in re.finditer(r"(\d+) failed", out):
        failed = int(m.group(1))
    for m in re.finditer(r"(\d+) skipped", out):
        skipped = int(m.group(1))
    duration = ""
    if m := re.search(r"in ([\d.]+)s", out):
        duration = m.group(1) + "s"

    # Per-file breakdown: "tests/unit/test_foo.py::test_bar PASSED"
    lines = out.splitlines()
    by_file: dict[str, list[str]] = {}
    for line in lines:
        if "::" in line and ("PASSED" in line or "FAILED" in line or "SKIPPED" in line):
            left, right = line.split("::", 1)
            filepath = left.strip()
            test_part = right.strip()
            by_file.setdefault(filepath, []).append(test_part)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    report_path = REPORTS_DIR / f"report_{timestamp}.md"
    with open(report_path, "w") as f:
        f.write("# Test report\n\n")
        f.write(f"**Generated:** {datetime.now().isoformat()}\n\n")
        f.write("## Summary\n\n")
        f.write(f"- Passed: {passed}\n")
        f.write(f"- Failed: {failed}\n")
        f.write(f"- Skipped: {skipped}\n")
        if duration:
            f.write(f"- Duration: {duration}\n\n")
        f.write("## By file\n\n")
        for filepath in sorted(by_file.keys()):
            f.write(f"### {filepath}\n\n")
            for item in by_file[filepath]:
                f.write(f"- {item}\n")
            f.write("\n")

    latest = REPORTS_DIR / "latest.md"
    latest.write_text(report_path.read_text())
    print(f"Report written to {report_path} and {latest}", file=sys.stderr)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
