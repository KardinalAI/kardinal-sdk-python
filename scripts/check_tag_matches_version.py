"""Fail unless a release tag (vX.Y.Z) matches the installed kardinal-ai
version. Run by .github/workflows/publish.yml before building, after
`pip install .`, so a mistyped tag can't publish a mislabeled release.

Usage: python scripts/check_tag_matches_version.py v1.0.0
"""

import sys
from importlib.metadata import version


def main(tag: str) -> int:
    expected = f"v{version('kardinal-ai')}"
    if tag != expected:
        print(
            f"Tag {tag!r} doesn't match the package version: expected {expected!r} "
            "(update the version in pyproject.toml, or fix the tag).",
            file=sys.stderr,
        )
        return 1
    print(f"Tag {tag!r} matches the package version.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
