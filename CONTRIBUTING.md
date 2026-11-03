# Contributing to the Kardinal Python SDK

## Reporting a bug or asking for a change

Open an issue: https://github.com/KardinalAI/kardinal-sdk-python/issues.
Include the SDK version (`kardinal version`, or
`pip show kardinal-ai`), your Python version, and what you did, expected
and got. Never paste your API key in an issue.

Pull requests are not accepted for now: this GitHub repository is a
read-only mirror of our internal repository, so a pull request opened here
can't be merged. Please open an issue instead.

For questions about your account, credits or quotas, contact
customer.success@kardinal.ai.

## For maintainers

The rest of this file is for the team working on the SDK itself. For using
it, see `README.md`.

### Setup and checks

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

bash scripts/generate_models.sh          # regenerate kardinal/routing/models/
pytest -q
mypy                                     # type check (config in pyproject.toml)
```

CI runs `pytest -q` and `mypy` on every supported Python version (3.10 to
3.14, see `.gitlab-ci.yml`), then builds the sdist and the wheel and runs
`twine check --strict` on them.

### Releasing

Releases are published to PyPI by `.github/workflows/publish.yml`, on the
GitHub mirror, with Trusted Publishing: no API token is stored anywhere.

1. Run `python scripts/sync_doc_examples.py --check` and
   `bash scripts/check_spec_matches_mintlify.sh` (see "The doc examples" and
   "The spec"): the copy of the docs examples and the spec must match the
   docs repository.
2. Open a merge request that sets the new `version` in `pyproject.toml`,
   and merge it.
3. Create the tag `vX.Y.Z` (matching that version) on the source
   repository, on the merged commit. The push mirror copies it to GitHub
   within minutes. Don't create tags on GitHub: the mirror would overwrite
   them.
4. On GitHub, the workflow tests, checks that the tag matches the package
   version, builds the sdist and the wheel, then waits in the `pypi`
   environment for a reviewer's approval (Actions tab). Once approved, it
   publishes to https://pypi.org/project/kardinal-ai/.

For a dry run, start the workflow by hand on GitHub (Actions → Publish →
Run workflow, on `main`): after approval in the `testpypi` environment, it
publishes to https://test.pypi.org/project/kardinal-ai/ instead.

TestPyPI, like PyPI, never accepts the same version twice. A dry run
therefore publishes a pre-release, `X.Y.Z.devN`, N being the workflow run
number (for instance `1.0.0.dev2`): `scripts/set_dev_version.py` sets it in
the CI checkout only, so nothing is committed and every dry run gets its
own version. To install one: `pip install --index-url
https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/
kardinal-ai==X.Y.Z.devN`. A real release (a `vX.Y.Z` tag) always publishes
the version from `pyproject.toml` as is.

The TypeScript SDK has no such test registry: its pre-releases go to the
real npm registry, kept off `latest` by the `next` dist-tag.

### The spec

`spec/openapi.yaml` is a copy of the `openapi.yaml` of the Kardinal API docs,
whose source repository is internal (the published version is at
https://developers.kardinal.ai/openapi.yaml). It isn't fetched at build
time. Maintainers with access to the docs repository check it hasn't
drifted before a release:

```bash
bash scripts/check_spec_matches_mintlify.sh
```

By default this compares against mintlify's published spec
(`origin/main`, read with `git show` from `../mintlify`, or
`MINTLIFY_REPO_PATH`), without checking anything out there; run
`git -C <mintlify repo> fetch` first to compare against the latest main.
`MINTLIFY_REF` picks another ref, and an explicit file path as first
argument is compared as-is. To resync:

```bash
git -C <mintlify repo> show origin/main:openapi.yaml > spec/openapi.yaml
bash scripts/generate_models.sh
```

Never hand-edit `kardinal/routing/models/`: it's overwritten on every
regeneration. Notes on generated models that pydantic specifically needs
(not the API itself) live in `kardinal/routing/_annotations.py`, reapplied
after every regeneration.

### The doc examples

The ```python blocks of the docs pages (`sdks/**/*.mdx` and `guides/*.mdx`
of the docs repository) are copied into `tests/doc_examples/`, and
`tests/test_doc_examples.py` runs them against a mocked API, so a docs
example that the SDK no longer supports fails the suite. The docs
repository isn't readable from CI, hence the copy. Refresh it after a docs
change, and check it hasn't drifted before a release:

```bash
python scripts/sync_doc_examples.py           # rewrite tests/doc_examples/
python scripts/sync_doc_examples.py --check   # exit 1 if the copy differs
```

When a release changes doc examples that are merged only after PyPI
publishes, run the check with `MINTLIFY_REF=<docs branch>`, and resync the
copy at `origin/main` once that branch has merged.

Like the spec check, it reads the pages with `git show` from `../mintlify`
(or `MINTLIFY_REPO_PATH`) at `origin/main` (or `MINTLIFY_REF`), without
checking anything out there; run `git -C <mintlify repo> fetch` first.

The same script also copies the "Full payload" block of each case-study
page (`case-studies/cold-chain-last-mile.mdx` and
`case-studies/parcel-express.mdx`) into `tests/case_studies/`, selected by
the title of its accordion, and `--check` covers that folder too: run it
before each release. `tests/test_examples.py` compares
`examples.cold_chain_plan()` and `examples.parcel_express_plan()` with these
copies.

What stays stable about those two functions is their names and their
`PlanCreate` return type. Their content follows the published page and may
change in any release; the TypeScript SDK follows the same rule. It copies the
same blocks with its own script (`scripts/sync-doc-examples.mjs`) into
`tests/case-studies/`.

### Code generation notes

- `scripts/generate_models.sh` passes `--disable-timestamp`:
  `datamodel-codegen` otherwise stamps a `# timestamp: ...` header that
  changes on every run, which would make the "no diff" check
  (`tests/test_models_no_diff.py`) fail on every pipeline regardless of
  whether anything actually changed.
- Three generator flags shape the models: `--use-subclass-enum` makes
  enums `str` subclasses (so `state == "optimized"` and `json.dumps` work),
  `--collapse-root-models` unwraps single-value wrappers so ids, versions
  and waypoints are plain values with no `.root`, and
  `--set-default-enum-member` gives an enum field its spec default as a
  member.
- Post-processing in `scripts/generate_models.sh`, applied on every
  regeneration, never by editing the generated file:
  - an `ast` step inlines every wrapper the generator leaves (a reference
    with a description, `allOf: [$ref]`, or a list with one kind of member)
    as plain types, or as
    an `Annotated[...]` alias when the wrapper carries a pattern or other
    constraint, so the constraint is still checked; it also restores
    `discriminator='type'` on every union whose members all declare a `type`
    literal, which the collapse drops;
  - the trailing `model_rebuild()` calls are sorted, to keep the output
    byte-identical across Python builds.
- Enums print as their value (`str(PlanState.optimized)` is `optimized`, on
  every Python version): `__str__` and `__format__` are patched on each
  generated enum when `kardinal.routing.models` is imported
  (`kardinal/routing/_annotations.py`).
- The patches in `kardinal/routing/_annotations.py` (the `PlanId` one and
  enum printing, among others) are applied when the models are imported,
  because the generated module ends by importing it; importing the models on
  their own is therefore enough, whatever the entry point.
- The webhook endpoints are marked `x-excluded` in the spec and are not
  implemented by this SDK.
- Enum values this SDK version doesn't know (a new plan state, warning
  code, ...) are kept when parsing a response, never when validating a plan
  built by hand: `validate_response()` in `kardinal/routing/_annotations.py`.

### Differences with the TypeScript SDK

The two SDKs behave the same; what differs, on purpose or by the nature of
each stack:

- Local validation: the TypeScript SDK validates `orders`, `stops`,
  `resources` and the top-level fields with the same rules, but not the
  inside of the rarer nested objects (`cost`, `breaks`, `objectives`,
  constraints, ...), and it keeps unknown fields there. pydantic, here,
  also accepts strings for numbers and booleans (`"1"`, `"true"`), which
  Zod rejects.
- Timeout: `httpx` applies `timeout` to each phase of a request; the
  TypeScript SDK's `timeoutMs` covers the whole request, response included.
- Validation messages (`plans validate`): the wording of pattern, missing
  field and unknown field errors is shared; other messages come from
  pydantic here and from Zod there.
- Version numbers: the two SDKs no longer share a version number from
  2.0.0. Python 2.0.0 removed `.root` (ids, versions, states and waypoints
  are plain values), a break the TypeScript SDK never had; each SDK
  follows its own numbering.
- Pre-releases: TestPyPI here, the npm `next` dist-tag there.

### What we don't want

The shape a full SDK generator would produce, which this SDK deliberately
does not reproduce:

```python
from kardinal_client.api.plan import get_plan          # one import per endpoint
result = get_plan.sync(plan_id="p1", client=client)    # error returned, not raised
# -> EnvelopedErrors | EnvelopedPlan | None: untangle it on every call
```
