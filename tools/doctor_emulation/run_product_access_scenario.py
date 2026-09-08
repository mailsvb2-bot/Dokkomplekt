"""Live GUI smoke for the production create/access/publication boundary.

Unlike the general doctor-emulation matrix this scenario deliberately enables
product access before pressing the real create command. It uses an isolated
license directory so it cannot consume a developer/user trial.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))

from doctor_sim import DoctorSim, make_docx  # noqa: E402


def main() -> None:
    sim = DoctorSim()
    try:
        access_dir = sim.root_dir / "production-access"
        os.environ["DOKKOMPLEKT_TEST_DISABLE_PRODUCT_ACCESS"] = "0"
        os.environ["DOKKOMPLEKT_LICENSE_DIR"] = str(access_dir)

        primary = sim.root_dir / "production-access-primary.docx"
        make_docx(
            primary,
            [
                "История болезни № 777/26. Пациент: Иванов Иван Иванович, 1980 г.р.",
                "Дата поступления: 05.09.2026. Дата выписки: 08.09.2026.",
                "Диагноз: F32.1 Депрессивный эпизод средней степени.",
                "Лечение: сертралин 100 мг утром.",
            ],
        )
        texts = sim.root_dir / "production-access-texts-F32.docx"
        make_docx(texts, ["Состояние стабильное. Контактен, ориентирован."])

        sim.drop(primary)
        sim.answers["openfilenames"] = (str(texts),)
        sim.app.choose_status_files()
        sim.create_diaries()
        sim.pump(0.4)

        outputs = [path for path in sim.outputs() if path.suffix.lower() == ".docx"]
        if sim.errors:
            raise AssertionError("real create command showed errors: " + " | ".join(sim.errors))
        if not outputs:
            raise AssertionError("real create command published no DOCX with product access enabled")

        from product_access.native import NativeProductAccessManager

        state = NativeProductAccessManager(storage_dir=access_dir).current_state()
        if state.plan != "trial" or not state.active:
            raise AssertionError(f"unexpected product-access state: {state.plan}/{state.reason}")
        if state.documents_used_total_trial < len(outputs):
            raise AssertionError(
                f"published {len(outputs)} files but usage accounting is only {state.documents_used_total_trial}"
            )
        if not all(path.exists() and path.stat().st_size > 0 for path in outputs):
            raise AssertionError("one or more published outputs are missing/empty")

        print(f"PRODUCTION CREATE ACCESS GUI SMOKE OK files={len(outputs)} used={state.documents_used_total_trial}")
    finally:
        sim.close()
        os.environ["DOKKOMPLEKT_TEST_DISABLE_PRODUCT_ACCESS"] = "1"
        os.environ.pop("DOKKOMPLEKT_LICENSE_DIR", None)


if __name__ == "__main__":
    main()
