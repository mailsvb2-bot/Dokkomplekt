from __future__ import annotations

from types import SimpleNamespace

from actions_creation_execution import ActionsCreationExecutionMixin


class _Harness(ActionsCreationExecutionMixin):
    pass


def test_legacy_discharge_button_routes_to_doctor_owned_vypisnoy_template_even_if_flag_inference_fails(monkeypatch):
    import universal_main_documents

    def broken_flags(_documents):
        raise RuntimeError("emulated flag scanner failure")

    monkeypatch.setattr(universal_main_documents, "custom_requirement_flags_for_documents", broken_flags)
    document = SimpleNamespace(
        id="doctor_vypisnoy",
        role_id="",
        category="regular",
        button_label="Выписной",
        template="templates/vypisnoy.docx",
        description="",
    )

    assert _Harness()._profile_document_matches_builtin_kind(document, "discharge") is True
