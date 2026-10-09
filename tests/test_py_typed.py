"""PEP 561: without this marker in the installed package, a user's mypy or
pyright skips `kardinal` entirely — every annotation in it is invisible to
them, and `plan.resourcess` or a wrong argument type is reported nowhere.

That it also reaches the *wheel* is checked by the build job in
.gitlab-ci.yml, which already builds one. A pytest version of that needed
`build` installed before the tests, which it isn't, so it skipped every run
and looked like coverage while checking nothing.
"""

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def test_the_marker_is_in_the_package() -> None:
    assert (_ROOT / "kardinal" / "py.typed").is_file()
