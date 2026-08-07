#!/usr/bin/env python3
"""
PostToolUse hook: after Claude Code edits a scoring-related file,
automatically run the scoring test suite and surface failures.

This is intentionally narrow in scope (only fires on scoring-related
paths) so it doesn't slow down unrelated edits (templates, docs, etc).
"""
import json
import subprocess
import sys

SCORING_PATH_MARKERS = ("scoring", "test_scoring")


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        # If we can't parse the hook payload, don't block anything.
        return 0

    file_path = (
        payload.get("tool_input", {}).get("file_path")
        or payload.get("tool_input", {}).get("path")
        or ""
    )

    if not any(marker in file_path.replace("\\", "/") for marker in SCORING_PATH_MARKERS):
        return 0  # not a scoring-related file, nothing to do

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_scoring.py", "-q"],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        print(
            "\nScoring tests failed after this edit. Fix before continuing.",
            file=sys.stderr,
        )
        return 2  # non-zero, non-blocking-but-visible exit for Claude Code to see

    print("Scoring tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
