from __future__ import annotations

import builtins
import importlib


def test_sitecustomize_exports_non_working_day_helper() -> None:
    import sitecustomize

    importlib.reload(sitecustomize)

    assert callable(getattr(builtins, "is_non_working_day", None))
