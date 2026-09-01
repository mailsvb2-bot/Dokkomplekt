from __future__ import annotations

DOCUMENT_INTELLIGENCE_CORE_LOCK_VERSION = "v1.0"


def assert_document_intelligence_core_lock() -> None:
    if DOCUMENT_INTELLIGENCE_CORE_LOCK_VERSION != "v1.0":
        raise AssertionError("Document intelligence core lock version changed unexpectedly")
