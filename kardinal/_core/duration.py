"""ISO 8601 duration parsing, written from scratch against the `Duration`
pattern in openapi.yaml (`^P(\\d+Y)?(\\d+M)?(\\d+W)?(\\d+D)?(T(\\d+H)?(\\d+M)?(\\d+S)?)?$`).

Stdlib only, no `pandas`: a plain function is all a client library needs
here, and it keeps `pip install kardinal-ai` at two dependencies.
"""

from __future__ import annotations

import re
from datetime import timedelta

_PATTERN = re.compile(
    r"^P"
    r"(?:(?P<years>\d+)Y)?"
    r"(?:(?P<months>\d+)M)?"
    r"(?:(?P<weeks>\d+)W)?"
    r"(?:(?P<days>\d+)D)?"
    r"(?:T"
    r"(?:(?P<hours>\d+)H)?"
    r"(?:(?P<minutes>\d+)M)?"
    r"(?:(?P<seconds>\d+)S)?"
    r")?$"
)

_DAYS_PER_YEAR = 365
_DAYS_PER_MONTH = 30


def parse_duration(value: str) -> timedelta:
    """Parse an ISO 8601 duration string (e.g. `PT5M`, `P1DT2H`) into a `timedelta`.

    `Y`/`M` (calendar year/month) are approximated as 365/30 days, since a
    `timedelta` has no calendar concept. `maxOptimizationDuration` and the
    other `Duration` fields in this API are always specified in `D`/`T`
    units in practice, so the approximation is not expected to matter.
    """
    match = _PATTERN.match(value)
    if match is None or value in ("P", "PT"):
        raise ValueError(f"Not a valid ISO 8601 duration: {value!r}")
    parts = {key: int(part) for key, part in match.groupdict(default="0").items()}
    return timedelta(
        days=parts["years"] * _DAYS_PER_YEAR
        + parts["months"] * _DAYS_PER_MONTH
        + parts["weeks"] * 7
        + parts["days"],
        hours=parts["hours"],
        minutes=parts["minutes"],
        seconds=parts["seconds"],
    )
