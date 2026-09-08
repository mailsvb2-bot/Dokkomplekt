from __future__ import annotations

from pathlib import Path

import actions_creation_live_guard as guard_module
from actions_creation_live_guard import ActionsCreationLiveGuardMixin
from actions_creation_orchestrator import ActionsCreationOrchestratorMixin


class _SuccessOwner:
    def __init__(self) -> None:
        self.calls: list[bool] = []
        self.statuses: list[str] = []
        self._active_patient_output_dir = Path("C:/result/patient")
        self.required_ok = True

    def create_selected_outputs(self, *, print_after: bool = False) -> bool:
        self.calls.append(print_after)
        return True

    def _set_status(self, value: str) -> None:
        self.statuses.append(value)

    def _prompt_missing_required_fields_or_continue(self, _review) -> bool:
        return self.required_ok


class _SuccessApp(ActionsCreationLiveGuardMixin, _SuccessOwner):
    pass


class _FailingOwner(_SuccessOwner):
    def create_selected_outputs(self, *, print_after: bool = False) -> bool:
        self.calls.append(print_after)
        raise RuntimeError("live generation exploded")


class _FailingApp(ActionsCreationLiveGuardMixin, _FailingOwner):
    pass


def test_creation_orchestrator_routes_main_action_through_live_guard() -> None:
    assert ActionsCreationOrchestratorMixin.__mro__[1] is ActionsCreationLiveGuardMixin


def test_main_create_action_continues_directly_after_required_fields() -> None:
    app = _SuccessApp()
    marker = object()
    assert app._confirm_patient_case_before_creation(marker) is True
    app.required_ok = False
    assert app._confirm_patient_case_before_creation(marker) is False


def test_main_create_action_delegates_once_and_reports_final_folder() -> None:
    app = _SuccessApp()
    assert app.create_selected_outputs(print_after=False) is True
    assert app.calls == [False]
    assert app.statuses[0].startswith("Проверяю данные")
    assert app.statuses[-1] == "Готово: файлы сохранены — C:/result/patient"


def test_unexpected_live_create_exception_is_never_invisible(monkeypatch) -> None:
    app = _FailingApp()
    shown: list[tuple[str, str]] = []
    monkeypatch.setattr(guard_module, "record_classified_error", lambda *args, **kwargs: None)
    monkeypatch.setattr(guard_module.messagebox, "showerror", lambda title, text: shown.append((title, text)))

    assert app.create_selected_outputs(print_after=False) is False
    assert app.calls == [False]
    assert shown and shown[0][0] == "Документы не созданы"
    assert "live generation exploded" in shown[0][1]
    assert app.statuses[-1] == "Создание не выполнено: показана ошибка"
