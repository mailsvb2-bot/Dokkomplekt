from __future__ import annotations

"""Local tariff, trial and license contract for Dokkomplekt.

Stores only product metadata. Never store/read/send patient documents, names,
diagnoses, template contents or patient file names here.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib, hmac, json, os, platform, uuid
from pathlib import Path
from typing import Any, Mapping

PRODUCT_ACCESS_CONTRACT_VERSION = "v1.0"
NO_PATIENT_DATA_IN_LICENSE_STATE = True
LOCAL_ONLY_PRODUCT_ACCESS = True
TRIAL_WATERMARK_TEXT = "ПРОБНАЯ ВЕРСИЯ. НЕ ИСПОЛЬЗОВАТЬ КАК МЕДИЦИНСКИЙ ДОКУМЕНТ."
EXPIRED_DEMO_WATERMARK_TEXT = "ДЕМО-ДОКУМЕНТ. ЛИЦЕНЗИЯ НЕ АКТИВНА."


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def parse_dt(value: str | None) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        raw = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
        dt = datetime.fromisoformat(raw)
        return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    except ValueError:
        return None


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def month_key(now: datetime | None = None) -> str:
    return (now or utc_now()).strftime("%Y-%m")


def stable_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def machine_fingerprint() -> str:
    raw = "|".join(str(x or "").lower() for x in (platform.system(), platform.machine(), platform.node(), os.getenv("COMPUTERNAME"), os.getenv("PROCESSOR_IDENTIFIER"), uuid.getnode()))
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:32]


@dataclass(frozen=True)
class PlanLimits:
    plan_id: str; title: str; monthly_price_rub: int; yearly_price_rub: int
    included_machines: int; included_users: int; profile_limit: int; template_limit: int
    document_limit_month: int; max_documents_per_run: int; watermark_mode: str = "none"
    batch_generation: bool = False; batch_print: bool = False; shared_department_profile: bool = False
    role_management: bool = False; offline_activation: bool = True; local_license_server: bool = False
    overage_percent: int = 20; grace_days: int = 7; support_level: str = "base"


PLAN_LIMITS: dict[str, PlanLimits] = {
    "trial": PlanLimits("trial", "Trial", 0, 0, 1, 1, 1, 5, 30, 3, "trial", offline_activation=False, overage_percent=0, grace_days=0, support_level="knowledge_base"),
    "doctor_start": PlanLimits("doctor_start", "Doctor Start", 1490, 14900, 1, 1, 1, 30, 600, 10),
    "doctor_pro": PlanLimits("doctor_pro", "Doctor Pro", 3900, 29900, 2, 1, 3, 150, 3000, 50, batch_generation=True, batch_print=True, support_level="priority"),
    "department": PlanLimits("department", "Department", 14900, 149000, 5, 10, 10, 500, 20000, 100, batch_generation=True, batch_print=True, shared_department_profile=True, role_management=True, grace_days=14, support_level="department"),
    "clinic": PlanLimits("clinic", "Clinic", 49000, 490000, 20, 50, 50, 2000, 100000, 250, batch_generation=True, batch_print=True, shared_department_profile=True, role_management=True, local_license_server=True, grace_days=30, support_level="sla"),
    "enterprise": PlanLimits("enterprise", "Enterprise", 0, 900000, 9999, 9999, 9999, 999999, 9999999, 1000, batch_generation=True, batch_print=True, shared_department_profile=True, role_management=True, local_license_server=True, grace_days=45, support_level="enterprise_sla"),
}


@dataclass(frozen=True)
class LicenseEntitlement:
    license_id: str; plan: str; owner_name: str = ""; organization_name: str = ""; seats: int = 1
    allowed_machines: tuple[str, ...] = (); valid_until: str = ""; issued_at: str = ""
    generation_limit_month: int | None = None; template_limit: int | None = None; profile_limit: int | None = None
    watermark_mode: str | None = None; offline_grace_days: int | None = None; features: tuple[str, ...] = (); signature: str = ""

    @classmethod
    def from_mapping(cls, p: Mapping[str, Any]) -> "LicenseEntitlement":
        return cls(str(p.get("license_id") or "").strip(), str(p.get("plan") or "").lower().strip(), str(p.get("owner_name") or "").strip(), str(p.get("organization_name") or "").strip(), max(1, int(p.get("seats") or 1)), tuple(str(x).lower().strip() for x in p.get("allowed_machines", ()) if str(x).strip()), str(p.get("valid_until") or "").strip(), str(p.get("issued_at") or "").strip(), int(p["generation_limit_month"]) if p.get("generation_limit_month") is not None else None, int(p["template_limit"]) if p.get("template_limit") is not None else None, int(p["profile_limit"]) if p.get("profile_limit") is not None else None, str(p.get("watermark_mode")).lower().strip() if p.get("watermark_mode") is not None else None, int(p["offline_grace_days"]) if p.get("offline_grace_days") is not None else None, tuple(str(x).strip() for x in p.get("features", ()) if str(x).strip()), str(p.get("signature") or "").strip())

    def unsigned_payload(self) -> dict[str, Any]:
        return {"license_id": self.license_id, "plan": self.plan, "owner_name": self.owner_name, "organization_name": self.organization_name, "seats": self.seats, "allowed_machines": list(self.allowed_machines), "valid_until": self.valid_until, "issued_at": self.issued_at, "generation_limit_month": self.generation_limit_month, "template_limit": self.template_limit, "profile_limit": self.profile_limit, "watermark_mode": self.watermark_mode, "offline_grace_days": self.offline_grace_days, "features": list(self.features)}

    def plan_limits(self) -> PlanLimits:
        if self.plan not in PLAN_LIMITS or self.plan == "trial": raise ValueError(f"Unknown paid license plan: {self.plan}")
        return PLAN_LIMITS[self.plan]

    def valid_until_dt(self) -> datetime | None: return parse_dt(self.valid_until)
    def is_expired(self, now: datetime | None = None) -> bool: return self.valid_until_dt() is None or (now or utc_now()) > self.valid_until_dt()
    def signature_expected(self, secret: str) -> str: return hmac.new(secret.encode(), stable_json(self.unsigned_payload()).encode(), hashlib.sha256).hexdigest()
    def signature_valid(self, secret: str) -> bool: return bool(self.signature and secret and hmac.compare_digest(self.signature, self.signature_expected(secret)))


@dataclass(frozen=True)
class LicenseState:
    plan: str; title: str; active: bool; reason: str; license_id: str = ""; owner_label: str = ""; valid_until: str = ""
    trial_started_at: str = ""; trial_ends_at: str = ""; days_left: int = 0; documents_used_month: int = 0
    documents_limit_month: int = 0; documents_used_total_trial: int = 0; remaining_documents_month: int = 0
    template_limit: int = 0; profile_limit: int = 0; included_machines: int = 1; watermark_mode: str = "none"; warning: str = ""
    @property
    def watermark_required(self) -> bool: return self.watermark_mode in {"trial", "expired_demo"}
    def watermark_text(self) -> str: return TRIAL_WATERMARK_TEXT if self.watermark_mode == "trial" else EXPIRED_DEMO_WATERMARK_TEXT if self.watermark_mode == "expired_demo" else ""


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool; code: str; title: str; message: str; state: LicenseState; warning: str = ""


class ProductAccessManager:
    def __init__(self, storage_dir: str | Path | None = None, now: datetime | None = None):
        self.storage_dir = Path(storage_dir) if storage_dir else self.default_storage_dir(); self.now = now
        self.storage_dir.mkdir(parents=True, exist_ok=True); self.state_path = self.storage_dir / "product_access_state.json"; self.license_path = Path(os.getenv("DOKKOMPLEKT_LICENSE_FILE") or self.storage_dir / "license.json")

    @staticmethod
    def default_storage_dir() -> Path:
        if os.getenv("DOKKOMPLEKT_LICENSE_DIR"): return Path(os.environ["DOKKOMPLEKT_LICENSE_DIR"]).expanduser()
        if os.getenv("LOCALAPPDATA"): return Path(os.environ["LOCALAPPDATA"]) / "Dokkomplekt"
        return Path.home() / ".dokkomplekt"

    def _now(self) -> datetime: return self.now or utc_now()
    def _load_state_payload(self) -> dict[str, Any]:
        try: return json.loads(self.state_path.read_text("utf-8")) if self.state_path.exists() else {}
        except Exception: return {}
    def _save_state_payload(self, p: Mapping[str, Any]) -> None:
        tmp = self.state_path.with_suffix(".tmp"); tmp.write_text(json.dumps(dict(p), ensure_ascii=False, indent=2, sort_keys=True), "utf-8"); os.replace(tmp, self.state_path)
    def _ensure_trial_started(self, p: dict[str, Any]) -> dict[str, Any]:
        if not p.get("trial_started_at"):
            p = dict(p); p["trial_started_at"] = iso(self._now()); p.setdefault("usage_by_month", {}); p.setdefault("trial_created_total", 0); self._save_state_payload(p)
        return p
    @staticmethod
    def _license_secret() -> str:
        if os.getenv("DOKKOMPLEKT_LICENSE_VERIFY_SECRET"): return os.environ["DOKKOMPLEKT_LICENSE_VERIFY_SECRET"].strip()
        try:
            from product_license_secret import LICENSE_VERIFY_SECRET  # type: ignore
            return str(LICENSE_VERIFY_SECRET or "").strip()
        except Exception: return ""
    def load_license(self) -> LicenseEntitlement | None:
        try:
            p = json.loads(self.license_path.read_text("utf-8")) if self.license_path.exists() else None
            return LicenseEntitlement.from_mapping(p) if isinstance(p, dict) else None
        except Exception: return None
    def install_license_text(self, text: str) -> LicenseState:
        p = json.loads(text or "{}");
        if not isinstance(p, dict): raise ValueError("Файл лицензии должен быть JSON-объектом.")
        ent = LicenseEntitlement.from_mapping(p); self._validate_license(ent, require_not_expired=False)
        tmp = self.license_path.with_suffix(".tmp"); tmp.write_text(json.dumps(ent.unsigned_payload() | {"signature": ent.signature}, ensure_ascii=False, indent=2, sort_keys=True), "utf-8"); os.replace(tmp, self.license_path)
        return self.current_state()
    def _validate_license(self, ent: LicenseEntitlement, *, require_not_expired: bool = True) -> None:
        if not ent.license_id: raise ValueError("В лицензии нет license_id.")
        if ent.plan not in PLAN_LIMITS or ent.plan == "trial": raise ValueError(f"Неизвестный тариф лицензии: {ent.plan!r}.")
        secret = self._license_secret(); unsigned_ok = os.getenv("DOKKOMPLEKT_ALLOW_UNSIGNED_LICENSES", "").lower() in {"1", "true", "yes", "on"}
        if secret and not ent.signature_valid(secret): raise ValueError("Подпись лицензии не прошла проверку.")
        if not secret and not unsigned_ok: raise ValueError("Подпись лицензии не может быть проверена в этой сборке.")
        if require_not_expired and ent.is_expired(self._now()): raise ValueError("Срок действия лицензии истёк.")
        if ent.allowed_machines and machine_fingerprint() not in ent.allowed_machines: raise ValueError("Лицензия не привязана к этому компьютеру.")
    def current_state(self) -> LicenseState:
        p = self._ensure_trial_started(self._load_state_payload()); usage = p.get("usage_by_month") if isinstance(p.get("usage_by_month"), dict) else {}; used = int(usage.get(month_key(self._now()), 0) or 0); trial_total = int(p.get("trial_created_total", 0) or 0); ent = self.load_license()
        if ent:
            try: self._validate_license(ent, require_not_expired=False); return self._paid_state(ent, used)
            except ValueError as exc: return self._blocked_state(str(exc), used, trial_total)
        return self._trial_state(p, used, trial_total)
    def _paid_state(self, ent: LicenseEntitlement, used: int) -> LicenseState:
        lim = ent.plan_limits(); valid = ent.valid_until_dt(); now = self._now(); grace = int(ent.offline_grace_days if ent.offline_grace_days is not None else lim.grace_days); expired = valid is None or now > valid; in_grace = bool(expired and valid and now <= valid + timedelta(days=grace))
        if expired and not in_grace: return self._blocked_state("Срок действия лицензии истёк.", used, 0)
        monthly = int(ent.generation_limit_month or lim.document_limit_month)
        return LicenseState(ent.plan, lim.title, True, "active_grace" if in_grace else "active", ent.license_id, ent.organization_name or ent.owner_name, ent.valid_until, days_left=max(0, int(((valid or now) - now).total_seconds() // 86400)), documents_used_month=used, documents_limit_month=monthly, remaining_documents_month=max(0, monthly - used), template_limit=int(ent.template_limit or lim.template_limit), profile_limit=int(ent.profile_limit or lim.profile_limit), included_machines=int(ent.seats or lim.included_machines), watermark_mode=str(ent.watermark_mode or lim.watermark_mode), warning=f"Лицензия истекла, действует льготный период {grace} дн." if in_grace else "")
    def _trial_state(self, p: Mapping[str, Any], used: int, trial_total: int) -> LicenseState:
        lim = PLAN_LIMITS["trial"]; start = parse_dt(str(p.get("trial_started_at") or "")) or self._now(); end = start + timedelta(days=14); active = self._now() <= end and trial_total < lim.document_limit_month
        return LicenseState("trial", lim.title, active, "trial_active" if active else "trial_document_limit" if trial_total >= lim.document_limit_month else "trial_expired", trial_started_at=iso(start), trial_ends_at=iso(end), days_left=max(0, int((end - self._now()).total_seconds() // 86400) + (1 if self._now() <= end else 0)), documents_used_month=used, documents_limit_month=lim.document_limit_month, documents_used_total_trial=trial_total, remaining_documents_month=max(0, lim.document_limit_month - trial_total), template_limit=lim.template_limit, profile_limit=lim.profile_limit, included_machines=lim.included_machines, watermark_mode=lim.watermark_mode if active else "expired_demo", warning="Пробная версия создаёт документы только с водяным знаком." if active else "Пробный период завершён.")
    def _blocked_state(self, reason: str, used: int, trial_total: int) -> LicenseState: return LicenseState("blocked", "Лицензия не активна", False, "blocked", documents_used_month=used, documents_used_total_trial=trial_total, watermark_mode="expired_demo", warning=reason)
    def check_document_creation(self, requested_count: int, *, template_count: int | None = None, profile_count: int | None = None) -> AccessDecision:
        count = max(1, int(requested_count or 1)); state = self.current_state()
        if not state.active: return AccessDecision(False, "license_inactive", "Лицензия не активна", state.warning or "Создание рабочих документов заблокировано.", state)
        lim = PLAN_LIMITS.get(state.plan, PLAN_LIMITS["trial"])
        if count > lim.max_documents_per_run: return AccessDecision(False, "per_run_limit", "Слишком много документов за один запуск", f"Тариф разрешает до {lim.max_documents_per_run} документов за один запуск. Выбрано: {count}.", state)
        if template_count is not None and int(template_count) > state.template_limit: return AccessDecision(False, "template_limit", "Превышен лимит шаблонов", f"Лимит тарифа: {state.template_limit} шаблонов.", state)
        if profile_count is not None and int(profile_count) > state.profile_limit: return AccessDecision(False, "profile_limit", "Превышен лимит профилей", f"Лимит тарифа: {state.profile_limit} профилей.", state)
        if state.plan == "trial":
            if count > state.remaining_documents_month: return AccessDecision(False, "trial_limit", "Пробный лимит исчерпан", "Пробная версия разрешает 30 созданных документов всего.", state)
            return AccessDecision(True, "ok_trial", "Пробная версия", "Документы будут созданы с пробным водяным знаком.", state, state.warning)
        hard = state.documents_limit_month + int(state.documents_limit_month * max(0, lim.overage_percent) / 100); projected = state.documents_used_month + count
        if state.documents_limit_month and projected > hard: return AccessDecision(False, "monthly_limit", "Месячный лимит документов исчерпан", f"Использовано {state.documents_used_month}/{state.documents_limit_month}; льготный перерасход исчерпан.", state)
        warning = state.warning or (f"Будет превышен месячный лимит {state.documents_limit_month}; действует льготный перерасход до {hard}." if state.documents_limit_month and projected > state.documents_limit_month else f"Использовано более 80% месячного лимита: после создания будет {projected}/{state.documents_limit_month}." if state.documents_limit_month and projected >= int(state.documents_limit_month * 0.8) else "")
        return AccessDecision(True, "ok", "Доступ разрешён", "Создание документов разрешено.", state, warning)
    def record_created_documents(self, count: int) -> None:
        delta = max(0, int(count or 0));
        if not delta: return
        p = self._ensure_trial_started(self._load_state_payload()); usage = p.get("usage_by_month") if isinstance(p.get("usage_by_month"), dict) else {}; key = month_key(self._now()); usage[key] = int(usage.get(key, 0) or 0) + delta; p["usage_by_month"] = usage
        if self.current_state().plan == "trial": p["trial_created_total"] = int(p.get("trial_created_total", 0) or 0) + delta
        p["updated_at"] = iso(self._now()); self._save_state_payload(p)
    def current_watermark_text(self) -> str: return self.current_state().watermark_text()
    def summary_text(self) -> str:
        s = self.current_state(); used = s.documents_used_total_trial if s.plan == "trial" else s.documents_used_month
        lines = [f"Тариф: {s.title}", f"Статус: {'активен' if s.active else 'не активен'}"]
        if s.owner_label: lines.append(f"Владелец: {s.owner_label}")
        if s.license_id: lines.append(f"Лицензия: {s.license_id}")
        if s.valid_until: lines.append(f"Действует до: {s.valid_until}")
        if s.trial_ends_at: lines.append(f"Пробный период до: {s.trial_ends_at}")
        if s.documents_limit_month: lines.append(f"Документы: {used} / {s.documents_limit_month}")
        lines += [f"Шаблоны: до {s.template_limit}", f"Профили: до {s.profile_limit}", f"Компьютеры: до {s.included_machines}"]
        if s.watermark_required: lines.append("Водяной знак: включён")
        if s.warning: lines.append(f"Предупреждение: {s.warning}")
        return "\n".join(lines)


def sign_license_payload(payload: Mapping[str, Any], secret: str) -> dict[str, Any]:
    ent = LicenseEntitlement.from_mapping(payload); unsigned = ent.unsigned_payload(); unsigned["signature"] = hmac.new(str(secret).encode(), stable_json(unsigned).encode(), hashlib.sha256).hexdigest(); return unsigned
