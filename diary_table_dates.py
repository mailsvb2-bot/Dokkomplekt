from __future__ import annotations

"""Compatibility marker for the removed legacy diary table date backend.

The active diary flow uses text-route generation with program-calendar dates.
This module intentionally does not expose legacy numeric helpers or table-row
removal logic; release checks keep it as a guard against accidental helper
reintroduction.
"""

LEGACY_DIARY_TABLE_DATES_BACKEND_REMOVED = True
