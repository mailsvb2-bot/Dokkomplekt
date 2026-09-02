from __future__ import annotations

from types import SimpleNamespace

from actions_creation_execution import ActionsCreationExecutionMixin


class _Harness(ActionsCreationExecutionMixin):
    pass


def test_legacy_discharge_route_never_guesses_from_human_label_or_path(monkeypatch):
    import universal_main_documents

    def broken_flags(_documents):
        raise RuntimeError("requirement helper is irrelevant to role routing")

    monkeypatch.setattr(universal_main_documents, "custom_requirement_flags_for_documents", broken_flags)
    document = SimpleNamespace(
        id="doctor_vypisnoy",
        role_id="",
        category="regular",
        button_label="Выписной",
        template="templates/vypisnoy.docx",
        description="выписной эпикриз",
    )
    assert _Harness()._profile_document_matches_builtin_kind(document, "discharge") is False


def test_legacy_discharge_route_uses_explicit_persisted_role():
    document = SimpleNamespace(
        id="stable-custom-id",
        role_id="discharge_epicrisis",
        category="medical",
        button_label="Любое переименованное название",
        template="templates/neutral-name.docx",
        description="",
    )
    assert _Harness()._profile_document_matches_builtin_kind(document, "discharge") is True
