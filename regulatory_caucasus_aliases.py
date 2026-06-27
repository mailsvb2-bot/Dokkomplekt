"""Caucasus regional aliases for medical-document recognition.

The regulatory advisor must remain gentle and non-blocking.  This module does
not claim to encode exact legal forms for Armenia, Georgia or Azerbaijan; it
adds multilingual markers commonly present in medical records so uploaded DOCX
from those regions can be recognized better by the same universal document-role
and section engine.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping

CAUCASUS_ALIAS_LOCK_VERSION = "v1.0"
CAUCASUS_ADVICE_IS_NON_BLOCKING = True
CAUCASUS_COUNTRIES = ("armenia", "georgia", "azerbaijan")


@dataclass(frozen=True)
class CaucasusCountryContext:
    id: str
    label: str
    languages: tuple[str, ...]
    source_note: str
    document_markers: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


CAUCASUS_COUNTRY_CONTEXTS: tuple[CaucasusCountryContext, ...] = (
    CaucasusCountryContext(
        id="armenia",
        label="Армения",
        languages=("ru", "hy", "en"),
        source_note=(
            "Закон Республики Армения о медицинской помощи и обслуживании населения закрепляет "
            "стационарную/амбулаторную организацию помощи, право пациента на сведения о состоянии здоровья, "
            "согласие/отказ от вмешательства и медицинские документы при отказе/экспертизе; в программе это "
            "используется только как справочная подсказка."
        ),
        document_markers=("բժշկական քարտ", "հիվանդության պատմություն", "ամբուլատոր քարտ", "էպիկրիզ"),
    ),
    CaucasusCountryContext(
        id="georgia",
        label="Грузия",
        languages=("ru", "ka", "en"),
        source_note=(
            "Для грузинских шаблонов добавлены языковые маркеры медицинской карты, направления, осмотра, "
            "выписки, согласия, операции, консультации, исследований и подписей. Подсказки не являются "
            "юридической проверкой формы."
        ),
        document_markers=("სამედიცინო ბარათი", "ავადმყოფობის ისტორია", "ამბულატორიული ბარათი", "ეპიკრიზი"),
    ),
    CaucasusCountryContext(
        id="azerbaijan",
        label="Азербайджан",
        languages=("ru", "az", "en"),
        source_note=(
            "Для азербайджанских шаблонов добавлены языковые маркеры медицинской карты, истории болезни, "
            "направления, выписки, операции, анестезии, исследований, комиссии и подписей. Подсказки остаются "
            "рекомендательными."
        ),
        document_markers=("tibbi kart", "xəstəlik tarixi", "ambulator kart", "epikriz", "çıxarış"),
    ),
)

FIELD_ALIASES: Mapping[str, tuple[str, ...]] = {
    "document.title": ("Փաստաթղթի անվանում", "დოკუმენტის დასახელება", "Sənədin adı"),
    "patient.fio": (
        "Պացիենտ", "Հիվանդ", "Անուն Ազգանուն", "Անուն, ազգանուն, հայրանուն", "Ա.Ա.Հ.",
        "პაციენტი", "ავადმყოფი", "სახელი გვარი", "სახელი, გვარი", "სახელი, გვარი, მამის სახელი",
        "Pasiyent", "Xəstə", "Soyad, ad, ata adı", "S.A.A.", "Adı, soyadı",
    ),
    "patient.birth_date": ("Ծննդյան ամսաթիվ", "დაბადების თარიღი", "Doğum tarixi"),
    "patient.age": ("Տարիք", "ასაკი", "Yaş"),
    "patient.sex": ("Սեռ", "სქესი", "Cins"),
    "patient.address": ("Հասցե", "Բնակության վայր", "მისამართი", "საცხოვრებელი ადგილი", "Ünvan", "Yaşayış yeri"),
    "patient.passport": ("Անձնագիր", "პასპორტი", "Şəxsiyyət vəsiqəsi", "Pasport"),
    "patient.snils": ("ՀՎՀՀ", "ID համար", "პირადი ნომერი", "Şəxsi nömrə", "FİN"),
    "case.number": ("Հիվանդության պատմություն №", "Բժշկական քարտ №", "ისტორიის №", "სამედიცინო ბარათის №", "Xəstəlik tarixi №", "Tibbi kart №"),
    "case.department": ("Բաժանմունք", "განყოფილება", "Şöbə"),
    "admission.date": ("Ընդունման ամսաթիվ", "Հոսպիտալացման ամսաթիվ", "მიღების თარიღი", "ჰოსპიტალიზაციის თარიღი", "Qəbul tarixi", "Hospitalizasiya tarixi"),
    "discharge.date": ("Դուրսգրման ամսաթիվ", "გაწერის თარიღი", "Çıxarılma tarixi"),
    "complaints": ("Գանգատներ", "ჩივილები", "Şikayətlər"),
    "anamnesis.life": ("Կյանքի անամնեզ", "ცხოვრების ანამნეზი", "Həyat anamnezi"),
    "anamnesis.disease": ("Հիվանդության անամնեզ", "დაავადების ანამნეზი", "Xəstəlik anamnezi"),
    "anamnesis.expert": ("Փորձագիտական անամնեզ", "ექსპერტული ანამნეზი", "Ekspert anamnezi"),
    "status.objective": ("Օբյեկտիվ վիճակ", "ობიექტური სტატუსი", "Obyektiv status"),
    "status.mental": ("Հոգեկան վիճակ", "ფსიქიკური სტატუსი", "Psixi status"),
    "status.somatic": ("Սոմատիկ վիճակ", "სომატური სტატუსი", "Somatik status"),
    "status.neurological": ("Նյարդաբանական վիճակ", "ნევროლოგიური სტატუსი", "Nevroloji status"),
    "diagnosis.main": ("Ախտորոշում", "Կլինիկական ախտորոշում", "დიაგნოზი", "კლინიკური დიაგნოზი", "Diaqnoz", "Klinik diaqnoz"),
    "diagnosis.icd10": ("ՀՄԴ-10", "ICD-10", "МКБ-10", "XBT-10"),
    "treatment.plan": ("Բուժման պլան", "Նշանակված բուժում", "მკურნალობის გეგმა", "დანიშნული მკურნალობა", "Müalicə planı", "Təyin olunmuş müalicə"),
    "treatment.summary": ("Կատարված բուժում", "ჩატარებული მკურნალობა", "Aparılmış müalicə"),
    "treatment.result": ("Բուժման արդյունք", "მკურნალობის შედეგი", "Müalicənin nəticəsi"),
    "condition.discharge": ("Վիճակը դուրսգրման պահին", "გაწერისას მდგომარეობა", "Çıxarılarkən vəziyyət"),
    "labs.results": ("Լաբորատոր հետազոտություններ", "Լաբորատոր արդյունքներ", "ლაბორატორიული კვლევები", "ლაბორატორიული შედეგები", "Laborator müayinələr", "Laborator nəticələr"),
    "labs.types": ("Հետազոտությունների տեսակներ", "კვლევის სახეები", "Müayinə növləri"),
    "instrumental.results": ("Գործիքային հետազոտություններ", "ინსტრუმენტული კვლევები", "Instrumental müayinələr"),
    "procedure.name": ("Վիրահատություն", "Միջամտություն", "ოპერაცია", "ჩარევა", "Əməliyyat", "Müdaxilə"),
    "procedure.date": ("Վիրահատության ամսաթիվ", "ოპერაციის თარიღი", "Əməliyyat tarixi"),
    "procedure.anesthesia": ("Անզգայացում", "Անեսթեզիա", "ანესთეზია", "გაუტკივარება", "Anesteziya", "Keyitmə"),
    "procedure.description": ("Վիրահատության ընթացք", "ოპერაციის მსვლელობა", "Əməliyyatın gedişi"),
    "procedure.complications": ("Բարդություններ", "გართულებები", "Ağırlaşmalar"),
    "postoperative.status": ("Հետվիրահատական վիճակ", "პოსტოპერაციული სტატუსი", "Əməliyyatdan sonrakı vəziyyət"),
    "vitals.blood_pressure": ("Զարկերակային ճնշում", "არტერიული წნევა", "Arterial təzyiq"),
    "vitals.pulse": ("Պուլս", "პულსი", "Nəbz"),
    "vitals.temperature": ("Ջերմաստիճան", "ტემპერატურა", "Temperatur"),
    "consent.informed": ("Տեղեկացված համաձայնություն", "ინფორმირებული თანხმობა", "Məlumatlandırılmış razılıq"),
    "consultation.reason": ("Խորհրդատվության պատճառ", "კონსულტაციის მიზეზი", "Məsləhətin səbəbi"),
    "consultant.specialty": ("Խորհրդատուի մասնագիտություն", "კონსულტანტის სპეციალობა", "Məsləhətçinin ixtisası"),
    "consultant.signature": ("Խորհրդատուի ստորագրություն", "კონსულტანტის ხელმოწერა", "Məsləhətçinin imzası"),
    "recommendations": ("Խորհուրդներ", "Առաջարկություններ", "რეკომენდაციები", "Tövsiyələr"),
    "doctor.name": ("Բժիշկ", "ექიმი", "Həkim"),
    "doctor.signature": ("Բժշկի ստորագրություն", "ექიმის ხელმოწერა", "Həkimin imzası"),
    "head.name": ("Բաժանմունքի վարիչ", "განყოფილების გამგე", "Şöbə müdiri"),
    "head.signature": ("Բաժանմունքի վարիչի ստորագրություն", "განყოფილების გამგის ხელმოწერა", "Şöbə müdirinin imzası"),
    "chief.name": ("Գլխավոր բժշկի տեղակալ", "მთავარი ექიმის მოადგილე", "Baş həkimin müavini"),
    "chief.signature": ("Գլխավոր բժշկի տեղակալի ստորագրություն", "მთავარი ექიმის მოადგილის ხელმოწერა", "Baş həkim müavinin imzası"),
    "commission.decision": ("Հանձնաժողովի որոշում", "კომისიის გადაწყვეტილება", "Komissiyanın qərarı"),
    "mse.referral_reason": ("Բժշկասոցիալական փորձաքննության հիմք", "სამედიცინო-სოციალური ექსპერტიზის საფუძველი", "Tibbi-sosial ekspertizaya göndərişin əsası"),
}

SECTION_ALIASES: Mapping[str, tuple[str, ...]] = {
    "patient_identity": ("Պացիենտ", "Հիվանդ", "პაციენტი", "ავადმყოფი", "Pasiyent", "Xəstə"),
    "case_admin": ("Հիվանդության պատմություն", "Բժշկական քարտ", "ავადმყოფობის ისტორია", "სამედიცინო ბარათი", "Xəstəlik tarixi", "Tibbi kart"),
    "admission": ("Ընդունում", "Հոսպիտալացում", "მიღება", "ჰოსპიტალიზაცია", "Qəbul", "Hospitalizasiya"),
    "discharge": ("Դուրսգրում", "գაწერა", "Çıxarış", "Çıxarılma"),
    "complaints": ("Գանգատներ", "ჩივილები", "Şikayətlər"),
    "anamnesis_disease": ("Հիվանդության անամնեզ", "დაავადების ანამნეზი", "Xəstəlik anamnezi"),
    "anamnesis_life": ("Կյանքի անամնեզ", "ცხოვრების ანამნეზი", "Həyat anamnezi"),
    "objective_status": ("Օբյեկտիվ վիճակ", "ობიექტური სტატუსი", "Obyektiv status"),
    "specialty_status": ("Հոգեկան վիճակ", "Նյարդաբանական վիճակ", "ფსიქიკური სტატუსი", "ნევროლოგიური სტატუსი", "Psixi status", "Nevroloji status"),
    "diagnosis": ("Ախտորոշում", "დიაგნოზი", "Diaqnoz"),
    "treatment": ("Բուժում", "მკურნალობა", "Müalicə"),
    "labs": ("Լաբորատոր հետազոտություններ", "ლაბორატორიული კვლევები", "Laborator müayinələr"),
    "instrumental": ("Գործիքային հետազոտություններ", "ინსტრუმენტული კვლევები", "Instrumental müayinələr"),
    "procedure": ("Վիրահատություն", "ოპერაცია", "Əməliyyat"),
    "anesthesia": ("Անեսթեզիա", "անզգայացում", "ანესთეზია", "Anesteziya"),
    "consent": ("Տեղեկացված համաձայնություն", "ინფორმირებული თანხმობა", "Məlumatlandırılmış razılıq"),
    "recommendations": ("Խորհուրդներ", "რეკომენდაციები", "Tövsiyələr"),
    "commission": ("Հանձնաժողով", "კომისია", "Komissiya", "Tibbi-sosial ekspertiza"),
    "signatures": ("Ստորագրություն", "ხელმოწერა", "İmza"),
}

ROLE_ALIASES: Mapping[str, tuple[str, ...]] = {
    "hospitalization_referral": ("Հոսպիտալացման ուղեգիր", "მიმართვა ჰოსპიტალიზაციაზე", "Hospitalizasiyaya göndəriş"),
    "admission_doctor_exam": ("Ընդունարանի բժշկի զննում", "მიმღები განყოფილების ექიმის გასინჯვა", "Qəbul şöbəsi həkiminin müayinəsi"),
    "primary_exam": ("Առաջնային զննում", "პირველადი გასინჯვა", "İlkin müayinə"),
    "inpatient_record": ("Հիվանդության պատմություն", "Բժշկական քարտ", "ავადმყოფობის ისტორია", "სამედიცინო ბარათი", "Xəstəlik tarixi", "Tibbi kart"),
    "daily_diary": ("Օրագիր", "Դինամիկ հսկողություն", "დღიური", "დინამიკური დაკვირვება", "Gündəlik", "Dinamik müşahidə"),
    "discharge_epicrisis": ("Դուրսգրման էպիկրիզ", "გაწერის ეპიკრიზი", "Çıxarış epikrizi"),
    "transfer_epicrisis": ("Տեղափոխման էպիկրիզ", "გადაყვანის ეპიკრიზი", "Köçürmə epikrizi"),
    "specialist_consultation": ("Խորհրդատվական եզրակացություն", "კონსულტაციური დასკვნა", "Məsləhətçi rəyi"),
    "operation_protocol": ("Վիրահատության արձանագրություն", "ოპერაციის ოქმი", "Əməliyyat protokolu"),
    "anesthesia_preop": ("Անեսթեզիոլոգի նախավիրահատական զննում", "ანესთეზიოლოგის წინასაოპერაციო გასინჯვა", "Anestezioloqun əməliyyatönü müayinəsi"),
    "informed_consent": ("Տեղեկացված համաձայնություն", "ინფორმირებული თანხმობა", "Məlumatlandırılmış razılıq"),
    "medical_commission": ("Բժշկական հանձնաժողով", "სამედიცინო კომისია", "Tibbi komissiya"),
    "mse_referral": ("Բժշկասոցիալական փորձաքննություն", "სამედიცინო-სოციალური ექსპერტიზა", "Tibbi-sosial ekspertiza"),
    "lab_results": ("Լաբորատոր արդյունքներ", "ლაბორატორიული შედეგები", "Laborator nəticələr"),
    "instrumental_study": ("Գործիքային հետազոտություն", "ინსტრუმენტული კვლევა", "Instrumental müayinə"),
}

ROLE_MARKERS: Mapping[str, tuple[str, ...]] = {
    "hospitalization_referral": ("ուղեգիր", "მიმართვა", "göndəriş", "hospitalizasiya"),
    "admission_doctor_exam": ("ընդունարան", "მიმღები განყოფილება", "qəbul şöbəsi"),
    "primary_exam": ("առաջնային", "პირველადი", "ilkin müayinə"),
    "inpatient_record": ("բժշկական քարտ", "հիվանդության պատմություն", "სამედიცინო ბარათი", "ავადმყოფობის ისტორია", "tibbi kart", "xəstəlik tarixi"),
    "daily_diary": ("օրագիր", "დღიური", "gündəlik", "dinamika"),
    "discharge_epicrisis": ("դուրսգրում", "გაწერა", "çıxarış", "epikriz"),
    "operation_protocol": ("վիրահատություն", "ოპერაცია", "əməliyyat"),
    "anesthesia_preop": ("անեսթեզիոլոգ", "ანესთეზიოლოგი", "anestezioloq"),
    "informed_consent": ("համաձայնություն", "თანხმობა", "razılıq"),
    "medical_commission": ("հանձնաժողով", "კომისია", "komissiya"),
    "lab_results": ("լաբորատոր", "ლაბორატორიული", "laborator"),
    "instrumental_study": ("հետազոտություն", "კვლევა", "müayinə"),
}

SPECIALTY_ALIASES: Mapping[str, tuple[str, ...]] = {
    "therapy": ("թերապևտ", "თერაპევტი", "Terapevt"),
    "surgery": ("վիրաբույժ", "ქირურგი", "Cərrah"),
    "neurology": ("նյարդաբան", "ნევროლოგი", "Nevroloq"),
    "dentistry": ("ատամնաբույժ", "სტომატოლოგი", "Stomatoloq"),
    "obstetrics": ("մանկաբարձ", "գինեկոլոգ", "მეანი", "გინეკოლოგი", "Ginekoloq", "Mama-ginekoloq"),
    "intensive_care": ("վերակենդանացում", "რეანიმაცია", "Reanimasiya"),
}


def field_aliases_for(field_id: str) -> tuple[str, ...]:
    return tuple(FIELD_ALIASES.get(str(field_id or "").strip().lower(), ()))


def section_aliases_for(section_id: str) -> tuple[str, ...]:
    return tuple(SECTION_ALIASES.get(str(section_id or "").strip().lower(), ()))


def role_aliases_for(role_id: str) -> tuple[str, ...]:
    return tuple(ROLE_ALIASES.get(str(role_id or "").strip().lower(), ()))


def role_markers_for(role_id: str) -> tuple[str, ...]:
    return tuple(ROLE_MARKERS.get(str(role_id or "").strip().lower(), ()))


def specialty_aliases_for(specialty_id: str) -> tuple[str, ...]:
    return tuple(SPECIALTY_ALIASES.get(str(specialty_id or "").strip().lower(), ()))


def caucasus_context_report() -> str:
    lines = ["Кавказский региональный контекст", ""]
    for item in CAUCASUS_COUNTRY_CONTEXTS:
        lines.append(f"{item.label}: {', '.join(item.document_markers)}")
        lines.append(f"  {item.source_note}")
    lines.append("")
    lines.append("Lock: подсказки по региональным маркерам не блокируют генерацию и не заменяют локальный шаблон врача.")
    return "\n".join(lines)


def assert_caucasus_alias_lock() -> None:
    if set(CAUCASUS_COUNTRIES) != {"armenia", "georgia", "azerbaijan"}:
        raise AssertionError("Caucasus alias context must cover Armenia, Georgia and Azerbaijan")
    if not CAUCASUS_ADVICE_IS_NON_BLOCKING:
        raise AssertionError("Caucasus regulatory aliases must remain non-blocking")
    report = caucasus_context_report().casefold()
    for required in ["Հիվանդության պատմություն", "სამედიცინო ბარათი", "Xəstəlik tarixi"]:
        if required.casefold() not in report:
            raise AssertionError(f"Missing Caucasus medical-record marker: {required}")
