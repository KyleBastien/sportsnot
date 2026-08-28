"""Package-level smoke test: draft_oracle imports and exposes a version."""

from __future__ import annotations

import draft_oracle


def test_package_exposes_version() -> None:
    assert isinstance(draft_oracle.__version__, str)
    assert draft_oracle.__version__.count(".") >= 1
