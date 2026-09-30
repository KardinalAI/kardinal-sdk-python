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
```

CI runs `pytest -q` on every supported Python version (3.10 to 3.14, see
`.gitlab-ci.yml`), then builds the sdist and the wheel and runs
`twine check --strict` on them.

### Releasing

Releases are published to PyPI by `.github/workflows/publish.yml`, on the
GitHub mirror, with Trusted Publishing: no API token is stored anywhere.

1. Open a merge request that sets the new `version` in `pyproject.toml`,
   and merge it.
2. Create the tag `vX.Y.Z` (matching that version) on the source
   repository, on the merged commit. The push mirror copies it to GitHub
   within minutes. Don't create tags on GitHub: the mirror would overwrite
   them.
3. On GitHub, the workflow tests, checks that the tag matches the package
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

### Code generation notes

- `scripts/generate_models.sh` passes `--disable-timestamp`:
  `datamodel-codegen` otherwise stamps a `# timestamp: ...` header that
  changes on every run, which would make the "no diff" check
  (`tests/test_models_no_diff.py`) fail on every pipeline regardless of
  whether anything actually changed.
- Two spec-level codegen defects are patched automatically rather than by
  editing the generated models: a double-`allOf` chain
  (`Plan.id -> PlanId -> UUID`) that otherwise makes `id`/`planId` fields
  unparsable (see `kardinal/routing/_annotations.py`), and two single-choice
  `oneOf` unions that carry a discriminator despite having nothing to
  discriminate, which otherwise makes the generated module fail to import
  entirely (see `scripts/generate_models.sh`).
- The `PlanId` patch above is applied when `kardinal.routing.plans` is
  imported, which every documented entry point (`Kardinal`, `routing.plans`,
  `routing.solutions`, `routing.examples`, the CLI) does first. Importing
  `kardinal.routing.models` on its own, bypassing all of those, will not
  have the patch applied. Not fixed at the `kardinal.routing` package level
  instead, since that would reintroduce `--help` loading the full models
  module (see `kardinal/routing/_annotations.py`'s docstring for the
  trade-off).
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
- Pre-releases: TestPyPI here, the npm `next` dist-tag there.

### What we don't want

The shape a full SDK generator would produce, which this SDK deliberately
does not reproduce:

```python
from kardinal_client.api.plan import get_plan          # one import per endpoint
result = get_plan.sync(plan_id="p1", client=client)    # error returned, not raised
# -> EnvelopedErrors | EnvelopedPlan | None: untangle it on every call
```
