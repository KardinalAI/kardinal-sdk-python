#!/usr/bin/env python3
"""Copies the ```python blocks of the Kardinal API docs pages into
tests/doc_examples/, where tests/test_doc_examples.py runs them against a
mocked API. The pages live in the docs repository (`../mintlify` by default),
which the CI runner cannot read: the copy is what CI runs, and this script
refreshes it.

Like scripts/check_spec_matches_mintlify.sh, it reads the pages with
`git show` at a ref (`origin/main` by default), never from the working tree,
which may hold unmerged doc work. Nothing is checked out or fetched there:
run `git -C <mintlify> fetch` first for the latest main.

    scripts/sync_doc_examples.py            rewrite tests/doc_examples/
    scripts/sync_doc_examples.py --check    exit 1 if the copy differs

    MINTLIFY_REPO_PATH=/path/to/mintlify MINTLIFY_REF=origin/main scripts/sync_doc_examples.py

Run `--check` before each release, like the spec check.
"""

import argparse
import ast
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "tests" / "doc_examples"

# Pages covered: sdks/**/*.mdx and guides/*.mdx.
_PAGE = re.compile(r"^(sdks/.+|guides/[^/]+)\.mdx$")

# Skip rules. A block that can't run against a mock is skipped by one of the
# rules below, never silently: every skip is printed, and a block that is not
# valid Python and matches no rule stops the script.
#
# Only ```python fences are copied; ```bash, ```json and the other languages
# (pip install, curl, CLI sessions, API payloads) never are.
SKIPPED_PAGES = {
    # Release notes: version numbers and old code shown as "before".
    "sdks/python/changelog.mdx": "changelog page",
    "sdks/typescript/changelog.mdx": "changelog page",
    # One signature per block (`k.routing.plans.get(plan_id: str) -> Plan`):
    # a shape, not code that runs.
    "sdks/python/reference.mdx": "signatures, not runnable code",
}

_FENCE = re.compile(r"^(?P<indent>[ \t]*)```python(?:[ \t].*)?$")


def _git(repo: str, *args: str) -> str:
    done = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if done.returncode != 0:
        sys.exit(f"git {' '.join(args)} failed in {repo}: {done.stderr.strip()}")
    return done.stdout


def _blocks(text: str):
    """Yields (line number of the opening fence, code) for each ```python block."""
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        match = _FENCE.match(lines[i])
        if not match:
            i += 1
            continue
        indent, start, body = match["indent"], i + 1, []
        i += 1
        while i < len(lines) and lines[i].strip() != "```":
            body.append(lines[i][len(indent):] if lines[i].startswith(indent) else lines[i])
            i += 1
        yield start, "\n".join(body) + "\n"
        i += 1


def build(repo: str, ref: str) -> dict:
    """The expected content of tests/doc_examples/, as {file name: text}."""
    files = {}
    pages = [p for p in _git(repo, "ls-tree", "-r", "--name-only", ref).split() if _PAGE.match(p)]
    for page in sorted(pages):
        if page in SKIPPED_PAGES:
            print(f"skipped {page}: {SKIPPED_PAGES[page]}", file=sys.stderr)
            continue
        parts = []
        for line, code in _blocks(_git(repo, "show", f"{ref}:{page}")):
            try:
                ast.parse(code)
            except SyntaxError as error:
                sys.exit(f"{page}:{line}: not valid Python ({error.msg}). Fix the page, or add a skip rule here.")
            parts.append(f"# --- {page}:{line}\n{code}")
        if parts:
            header = f"# Copied from {page} by scripts/sync_doc_examples.py: do not edit by hand.\n\n"
            files[page.removesuffix(".mdx").replace("/", "__") + ".py"] = header + "\n\n".join(parts)
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="exit 1 if tests/doc_examples/ differs")
    args = parser.parse_args()
    repo = os.environ.get("MINTLIFY_REPO_PATH", str(ROOT.parent / "mintlify"))
    ref = os.environ.get("MINTLIFY_REF", "origin/main")
    expected = build(repo, ref)
    present = {p.name: p.read_text() for p in OUT.glob("*.py")} if OUT.is_dir() else {}

    if args.check:
        drift = sorted(name for name in expected.keys() | present.keys() if expected.get(name) != present.get(name))
        if not drift:
            print(f"tests/doc_examples/ matches the doc pages at {ref} in {repo}.")
            return 0
        print(f"tests/doc_examples/ has drifted from the doc pages at {ref} in {repo}: {', '.join(drift)}")
        print("Run: scripts/sync_doc_examples.py")
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    for name in present.keys() - expected.keys():
        (OUT / name).unlink()
    for name, text in expected.items():
        (OUT / name).write_text(text)
    print(f"Wrote {len(expected)} files to tests/doc_examples/ from {ref} in {repo}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
