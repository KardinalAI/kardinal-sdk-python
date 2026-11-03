"""scripts/sync_doc_examples.py copies the "Full payload" block of a case-study
page, and only that block, so the test that compares an example plan with it
does not depend on how many JSON blocks the page has before it.
"""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "sync_doc_examples.py"
_spec = importlib.util.spec_from_file_location("sync_doc_examples", _SCRIPT)
sync = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sync)

_PAGE = """# Case study

```json
{"an": "earlier block"}
```

<Accordion title="Full payload — ready to submit as POST /plans">

```json
{
  "name": "full"
}
```

</Accordion>
"""


def test_the_full_payload_block_is_taken_not_an_earlier_json_block() -> None:
    assert sync.full_payload("case-studies/x.mdx", _PAGE) == '{\n  "name": "full"\n}\n'


def test_a_page_without_the_accordion_stops_the_script_with_a_message() -> None:
    with pytest.raises(SystemExit, match="case-studies/x.mdx.*Full payload"):
        sync.full_payload("case-studies/x.mdx", "```json\n{}\n```\n")


def test_a_full_payload_that_is_not_json_stops_the_script() -> None:
    page = '<Accordion title="Full payload">\n```json\n{oops\n```\n</Accordion>\n'
    with pytest.raises(SystemExit, match="not valid JSON"):
        sync.full_payload("case-studies/x.mdx", page)
