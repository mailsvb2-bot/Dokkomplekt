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

CAUCASUS_ALIAS_LOCK_VERSION = "v1.1"
CAUCASUS_ADVICE_IS_NON_BLOCKING = True
CAUCASUS_COUNTRIES = ("armenia", "georgia", "azerbaijan", "poland")


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
        id="poland",
        label="Польша",
        languages=("pl", "en"),
        source_note=(
            "Для польских DOCX/DOCM-шаблонов добавлены языковые маркеры медицинской карты, "
            "истории болезни, госпитализации, выписки, диагноза, лечения, согласия, исследований "
            "и подписей. Подсказки остаются рекомендательными: программа не навязывает форму страны "
            "и заполняет только шаблоны врача."
        ),
        document_markers=("historia choroby", "karta informacyjna", "karta leczenia", "epikryza", "rozpoznanie"),
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
    "document.title": ("Nazwa dokumentu", "Tytuł dokumentu", "Tytul dokumentu", "Փաստաթղթի անվանում", "დოკუმენტის დასახელება", "Sənədin adı"),
    "patient.fio": ("Pacjent", "Pacjentka", "Imię i nazwisko", "Imie i nazwisko", "Nazwisko i imię", "Nazwisko i imie", 
        "Պացիենտ", "Հիվանդ", "Անուն Ազգանուն", "Անուն, ազգանուն, հայրանուն", "Ա.Ա.Հ.",
        "პაციენტი", "ავადმყოფი", "სახელი გვარი", "სახელი, გვარი", "სახელი, გვარი, მამის სახელი",
        "Pasiyent", "Xəstə", "Soyad, ad, ata adı", "S.A.A.", "Adı, soyadı",
    ),
    "patient.birth_date": ("Data urodzenia", "Urodzony", "Urodzona", "Ծննդյան ամսաթիվ", "დაბადების თარიღი", "Doğum tarixi"),
    "patient.age": ("Wiek", "lat", "Տարիք", "ასაკი", "Yaş"),
    "patient.sex": ("Płeć", "Plec", "Սեռ", "სქესი", "Cins"),
    "patient.address": ("Adres", "Adres zamieszkania", "Miejsce zamieszkania", "Հասցե", "Բնակության վայր", "მისამართი", "საცხოვრებელი ადგილი", "Ünvan", "Yaşayış yeri"),
    "patient.passport": ("Paszport", "Dokument tożsamości", "Dokument tozsamosci", "Անձնագիր", "პასპორტი", "Şəxsiyyət vəsiqəsi", "Pasport"),
    "patient.snils": ("PESEL", "Nr PESEL", "Numer PESEL", "Identyfikator pacjenta", "ՀՎՀՀ", "ID համար", "პირადი ნომერი", "Şəxsi nömrə", "FİN"),
    "case.number": ("Nr historii choroby", "Numer historii choroby", "Historia choroby nr", "Historia choroby №", "Nr dokumentacji", "Numer dokumentacji", "Nr karty", "Հիվանդության պատմություն №", "Բժշկական քարտ №", "ისტორიის №", "სამედიცინო ბარათის №", "Xəstəlik tarixi №", "Tibbi kart №"),
    "case.department": ("Oddział", "Oddzial", "Klinika", "Բաժանմունք", "განყოფილება", "Şöbə"),
    "admission.date": ("Data przyjęcia", "Data przyjecia", "Data hospitalizacji", "Przyjęty", "Przyjeta", "Przyjęta", "Przyjety", "Hospitalizacja od", "Ընդունման ամսաթիվ", "Հոսպիտալացման ամսաթիվ", "მიღების თარიღი", "ჰოსპიტალიზაციის თარიღი", "Qəbul tarixi", "Hospitalizasiya tarixi"),
    "discharge.date": ("Data wypisu", "Data wypisania", "Wypisany", "Wypisana", "Wypisano", "Դուրսգրման ամսաթիվ", "გაწერის თარიღი", "Çıxarılma tarixi"),
    "complaints": ("Skargi", "Dolegliwości", "Dolegliwosci", "Skargi przy przyjęciu", "Skargi przy przyjeciu", "Գանգատներ", "ჩივილები", "Şikayətlər"),
    "anamnesis.life": ("Wywiad życiowy", "Wywiad zyciowy", "Wywiad osobniczy", "Կյանքի անամնեզ", "ცხოვრების ანამნეზი", "Həyat anamnezi"),
    "anamnesis.disease": ("Wywiad chorobowy", "Wywiad obecnej choroby", "Historia choroby", "Հիվանդության անամնեզ", "დაავადების ანამნეზი", "Xəstəlik anamnezi"),
    "anamnesis.expert": ("Wywiad ekspercki", "Wywiad zawodowy", "Փորձագիտական անամնեզ", "ექსპერტული ანამნეზი", "Ekspert anamnezi"),
    "status.objective": ("Stan przedmiotowy", "Badanie przedmiotowe", "Status praesens", "Օբյեկտիվ վիճակ", "ობიექტური სტატუსი", "Obyektiv status"),
    "status.mental": ("Stan psychiczny", "Badanie psychiatryczne", "Հոգեկան վիճակ", "ფსიქიკური სტატუსი", "Psixi status"),
    "status.somatic": ("Stan somatyczny", "Badanie somatyczne", "Սոմատիկ վիճակ", "სომატური სტატუსი", "Somatik status"),
    "status.neurological": ("Stan neurologiczny", "Badanie neurologiczne", "Նյարդաբանական վիճակ", "ნევროლოგიური სტატუსი", "Nevroloji status"),
    "diagnosis.main": ("Rozpoznanie", "Rozpoznanie kliniczne", "Diagnoza", "Rozpoznanie główne", "Rozpoznanie glowne", "Ախտորոշում", "Կլինիկական ախտորոշում", "დიაგნოზი", "კლინიკური დიაგნოზი", "Diaqnoz", "Klinik diaqnoz"),
    "diagnosis.icd10": ("ICD-10", "ICD10", "Kod ICD-10", "Kod rozpoznania", "MKB-10", "ՀՄԴ-10", "ICD-10", "МКБ-10", "XBT-10"),
    "treatment.plan": ("Leczenie", "Plan leczenia", "Zalecone leczenie", "Zastosowane leczenie", "Terapia", "Բուժման պլան", "Նշանակված բուժում", "მკურნალობის გეგმა", "დანიშნული მკურნალობა", "Müalicə planı", "Təyin olunmuş müalicə"),
    "treatment.summary": ("Przebieg leczenia", "Leczenie zastosowane", "Zastosowane leczenie", "Կատարված բուժում", "ჩატარებული მკურნალობა", "Aparılmış müalicə"),
    "treatment.result": ("Wynik leczenia", "Stan przy wypisie", "Բուժման արդյունք", "მკურნალობის შედეგი", "Müalicənin nəticəsi"),
    "condition.discharge": ("Stan przy wypisie", "Stan w chwili wypisu", "Վիճակը դուրսգրման պահին", "გაწერისას მდგომარეობა", "Çıxarılarkən vəziyyət"),
    "labs.results": ("Wyniki badań laboratoryjnych", "Badania laboratoryjne", "Laboratorium", "Wyniki badań", "Լաբորատոր հետազոտություններ", "Լաբորատոր արդյունքներ", "ლაბორატორიული კვლევები", "ლაბორატორიული შედეგები", "Laborator müayinələr", "Laborator nəticələr"),
    "labs.types": ("Rodzaje badań", "Zakres badań", "Հետազոտությունների տեսակներ", "კვლევის სახეები", "Müayinə növləri"),
    "instrumental.results": ("Badania obrazowe", "Badania instrumentalne", "Wyniki badań instrumentalnych", "Գործիքային հետազոտություններ", "ინსტრუმენტული კვლევები", "Instrumental müayinələr"),
    "procedure.name": ("Zabieg", "Operacja", "Procedura", "Nazwa zabiegu", "Վիրահատություն", "Միջամտություն", "ოპერაცია", "ჩარევა", "Əməliyyat", "Müdaxilə"),
    "procedure.date": ("Data zabiegu", "Data operacji", "Վիրահատության ամսաթիվ", "ოპერაციის თარიღი", "Əməliyyat tarixi"),
    "procedure.anesthesia": ("Znieczulenie", "Anestezja", "Rodzaj znieczulenia", "Անզգայացում", "Անեսթեզիա", "ანესთეზია", "გაუტკივარება", "Anesteziya", "Keyitmə"),
    "procedure.description": ("Przebieg operacji", "Opis zabiegu", "Przebieg zabiegu", "Վիրահատության ընթացք", "ოპერაციის მსვლელობა", "Əməliyyatın gedişi"),
    "procedure.complications": ("Powikłania", "Powiklania", "Բարդություններ", "გართულებები", "Ağırlaşmalar"),
    "postoperative.status": ("Stan pooperacyjny", "Okres pooperacyjny", "Հետվիրահատական վիճակ", "პოსტოპერაციული სტატუსი", "Əməliyyatdan sonrakı vəziyyət"),
    "vitals.blood_pressure": ("Ciśnienie tętnicze", "Cisnienie tetnicze", "RR", "Զարկերակային ճնշում", "არტერიული წნევა", "Arterial təzyiq"),
    "vitals.pulse": ("Tętno", "Tetno", "Puls", "Պուլս", "პულსი", "Nəbz"),
    "vitals.temperature": ("Temperatura", "Ciepłota ciała", "Cieplota ciala", "Ջերմաստիճան", "ტემპერატურა", "Temperatur"),
    "consent.informed": ("Świadoma zgoda", "Swiadoma zgoda", "Zgoda pacjenta", "Տեղեկացված համաձայնություն", "ინფორმირებული თანხმობა", "Məlumatlandırılmış razılıq"),
    "consultation.reason": ("Powód konsultacji", "Powod konsultacji", "Cel konsultacji", "Խորհրդատվության պատճառ", "კონსულტაციის მიზეზი", "Məsləhətin səbəbi"),
    "consultant.specialty": ("Specjalność konsultanta", "Specjalnosc konsultanta", "Խորհրդատուի մասնագիտություն", "კონსულტანტის სპეციალობა", "Məsləhətçinin ixtisası"),
    "consultant.signature": ("Podpis konsultanta", "Խորհրդատուի ստորագրություն", "კონსულტანტის ხელმოწერა", "Məsləhətçinin imzası"),
    "recommendations": ("Zalecenia", "Rekomendacje", "Խորհուրդներ", "Առաջարկություններ", "რეკომენდაციები", "Tövsiyələr"),
    "doctor.name": ("Lekarz", "Lekarz prowadzący", "Lekarz prowadzacy", "Բժիշկ", "ექიმი", "Həkim"),
    "doctor.signature": ("Podpis lekarza", "Lekarz podpis", "Բժշկի ստորագրություն", "ექიმის ხელმოწერა", "Həkimin imzası"),
    "head.name": ("Ordynator", "Kierownik oddziału", "Kierownik oddzialu", "Բաժանմունքի վարիչ", "განყოფილების გამგე", "Şöbə müdiri"),
    "head.signature": ("Podpis ordynatora", "Podpis kierownika oddziału", "Podpis kierownika oddzialu", "Բաժանմունքի վարիչի ստորագրություն", "განყოფილების გამგის ხელმოწერა", "Şöbə müdirinin imzası"),
    "chief.name": ("Zastępca dyrektora ds. medycznych", "Zastepca dyrektora ds. medycznych", "Գլխավոր բժշկի տեղակալ", "მთავარი ექიმის მოადგილე", "Baş həkimin müavini"),
    "chief.signature": ("Podpis zastępcy dyrektora", "Podpis zastepcy dyrektora", "Գլխավոր բժշկի տեղակալի ստորագրություն", "მთავარი ექიმის მოადგილის ხელმოწერა", "Baş həkim müavinin imzası"),
    "commission.decision": ("Decyzja komisji", "Orzeczenie komisji", "Հանձնաժողովի որոշում", "კომისიის გადაწყვეტილება", "Komissiyanın qərarı"),
    "mse.referral_reason": ("Powód skierowania na komisję", "Powod skierowania na komisje", "Բժշկասոցիալական փորձաքննության հիմք", "სამედიცინო-სოციალური ექსპერტიზის საფუძველი", "Tibbi-sosial ekspertizaya göndərişin əsası"),
}

SECTION_ALIASES: Mapping[str, tuple[str, ...]] = {
    "patient_identity": ("Pacjent", "Pacjentka", "Chory", "Chora", "Պացիենտ", "Հիվանդ", "პაციენტი", "ავადმყოფი", "Pasiyent", "Xəstə"),
    "case_admin": ("Historia choroby", "Dokumentacja medyczna", "Karta informacyjna", "Karta leczenia", "Հիվանդության պատմություն", "Բժշկական քարտ", "ავადმყოფობის ისტორია", "სამედიცინო ბარათი", "Xəstəlik tarixi", "Tibbi kart"),
    "admission": ("Przyjęcie", "Przyjecie", "Hospitalizacja", "Ընդունում", "Հոսպիտալացում", "მიღება", "ჰოსპიტალიზაცია", "Qəbul", "Hospitalizasiya"),
    "discharge": ("Wypis", "Wypisanie", "Karta informacyjna leczenia szpitalnego", "Դուրսգրում", "գაწერა", "Çıxarış", "Çıxarılma"),
    "complaints": ("Skargi", "Dolegliwości", "Dolegliwosci", "Գանգատներ", "ჩივილები", "Şikayətlər"),
    "anamnesis_disease": ("Wywiad chorobowy", "Historia choroby", "Հիվանդության անամնեզ", "დაავადების ანამნეზი", "Xəstəlik anamnezi"),
    "anamnesis_life": ("Wywiad życiowy", "Wywiad zyciowy", "Կյանքի անամնեզ", "ცხოვრების ანამნეზი", "Həyat anamnezi"),
    "objective_status": ("Stan przedmiotowy", "Badanie przedmiotowe", "Օբյեկտիվ վիճակ", "ობიექტური სტატუსი", "Obyektiv status"),
    "specialty_status": ("Stan psychiczny", "Stan neurologiczny", "Badanie specjalistyczne", "Հոգեկան վիճակ", "Նյարդաբանական վիճակ", "ფსიქიკური სტატუსი", "ნევროლოგიური სტატუსი", "Psixi status", "Nevroloji status"),
    "diagnosis": ("Rozpoznanie", "Diagnoza", "Ախտորոշում", "დიაგნოზი", "Diaqnoz"),
    "treatment": ("Leczenie", "Terapia", "Բուժում", "მკურნალობა", "Müalicə"),
    "labs": ("Badania laboratoryjne", "Wyniki badań", "Լաբորատոր հետազոտություններ", "ლაბორატორიული კვლევები", "Laborator müayinələr"),
    "instrumental": ("Badania obrazowe", "Badania instrumentalne", "Գործիքային հետազոտություններ", "ინსტრუმენტული კვლევები", "Instrumental müayinələr"),
    "procedure": ("Operacja", "Zabieg", "Procedura", "Վիրահատություն", "ოპერაცია", "Əməliyyat"),
    "anesthesia": ("Znieczulenie", "Anestezja", "Անեսթեզիա", "անզգայացում", "ანესთეზია", "Anesteziya"),
    "consent": ("Świadoma zgoda", "Swiadoma zgoda", "Zgoda", "Տեղեկացված համաձայնություն", "ინფორმირებული თანხმობა", "Məlumatlandırılmış razılıq"),
    "recommendations": ("Zalecenia", "Rekomendacje", "Խորհուրդներ", "რეკომენდაციები", "Tövsiyələr"),
    "commission": ("Komisja lekarska", "Komisja medyczna", "Հանձնաժողով", "კომისია", "Komissiya", "Tibbi-sosial ekspertiza"),
    "signatures": ("Podpis", "Podpisy", "Lekarz", "Ստորագրություն", "ხელმოწერა", "İmza"),
}

ROLE_ALIASES: Mapping[str, tuple[str, ...]] = {
    "hospitalization_referral": ("Skierowanie do szpitala", "Skierowanie na hospitalizację", "Skierowanie na hospitalizacje", "Հոսպիտալացման ուղեգիր", "მიმართვა ჰოსპიტალიზაციაზე", "Hospitalizasiyaya göndəriş"),
    "admission_doctor_exam": ("Badanie lekarza izby przyjęć", "Badanie lekarza izby przyjec", "Badanie w izbie przyjęć", "Ընդունարանի բժշկի զննում", "მიმღები განყოფილების ექიმის გასინჯვა", "Qəbul şöbəsi həkiminin müayinəsi"),
    "primary_exam": ("Badanie wstępne", "Badanie wstepne", "Badanie przy przyjęciu", "Badanie przy przyjeciu", "Առաջնային զննում", "პირველადი გასინჯვა", "İlkin müayinə"),
    "inpatient_record": ("Historia choroby", "Karta leczenia szpitalnego", "Dokumentacja medyczna", "Հիվանդության պատմություն", "Բժշկական քարտ", "ავადმყოფობის ისტორია", "სამედიცინო ბარათი", "Xəstəlik tarixi", "Tibbi kart"),
    "daily_diary": ("Dziennik obserwacji", "Dziennik lekarski", "Obserwacja dzienna", "Օրագիր", "Դինամիկ հսկողություն", "დღიური", "დინამიკური დაკვირვება", "Gündəlik", "Dinamik müşahidə"),
    "discharge_epicrisis": ("Karta informacyjna leczenia szpitalnego", "Epikryza wypisowa", "Wypis", "Դուրսգրման էպիկրիզ", "გაწერის ეპიკრიზი", "Çıxarış epikrizi"),
    "transfer_epicrisis": ("Epikryza przeniesieniowa", "Karta przeniesienia", "Տեղափոխման էպիկրիզ", "გადაყვანის ეპიკრიზი", "Köçürmə epikrizi"),
    "specialist_consultation": ("Konsultacja specjalistyczna", "Opinia konsultacyjna", "Խորհրդատվական եզրակացություն", "კონსულტაციური დასკვნა", "Məsləhətçi rəyi"),
    "operation_protocol": ("Protokół operacji", "Protokol operacji", "Opis operacji", "Վիրահատության արձանագրություն", "ოპერაციის ოქმი", "Əməliyyat protokolu"),
    "anesthesia_preop": ("Badanie anestezjologiczne", "Konsultacja anestezjologiczna", "Անեսթեզիոլոգի նախավիրահատական զննում", "ანესთეზიოლოგის წინასაოპერაციო გასინჯვა", "Anestezioloqun əməliyyatönü müayinəsi"),
    "informed_consent": ("Świadoma zgoda", "Swiadoma zgoda", "Zgoda pacjenta", "Տեղեկացված համաձայնություն", "ინფორმირებული თანხმობა", "Məlumatlandırılmış razılıq"),
    "medical_commission": ("Komisja lekarska", "Komisja medyczna", "Բժշկական հանձնաժողով", "სამედიცინო კომისია", "Tibbi komissiya"),
    "mse_referral": ("Skierowanie na komisję", "Skierowanie na komisje", "Բժշկասոցիալական փորձաքննություն", "სამედიცინო-სოციალური ექსპერტიზა", "Tibbi-sosial ekspertiza"),
    "lab_results": ("Wyniki badań laboratoryjnych", "Badania laboratoryjne", "Լաբորատոր արդյունքներ", "ლაბორატორიული შედეგები", "Laborator nəticələr"),
    "instrumental_study": ("Badanie obrazowe", "Badanie instrumentalne", "Գործիքային հետազոտություն", "ინსტრუმენტული კვლევა", "Instrumental müayinə"),
}

ROLE_MARKERS: Mapping[str, tuple[str, ...]] = {
    "hospitalization_referral": ("skierowanie", "hospitalizacja", "ուղեգիր", "მიმართვა", "göndəriş", "hospitalizasiya"),
    "admission_doctor_exam": ("izba przyjęć", "izba przyjec", "przyjęcie", "ընդունարան", "მიმღები განყოფილება", "qəbul şöbəsi"),
    "primary_exam": ("badanie wstępne", "badanie przy przyjęciu", "առաջնային", "პირველადი", "ilkin müayinə"),
    "inpatient_record": ("historia choroby", "karta leczenia", "dokumentacja medyczna", "բժշկական քարտ", "հիվանդության պատմություն", "სამედიცინო ბარათი", "ავადმყოფობის ისტორია", "tibbi kart", "xəstəlik tarixi"),
    "daily_diary": ("dziennik", "obserwacja", "notatka lekarska", "օրագիր", "დღიური", "gündəlik", "dinamika"),
    "discharge_epicrisis": ("wypis", "karta informacyjna", "epikryza", "դուրսգրում", "გაწერა", "çıxarış", "epikriz"),
    "operation_protocol": ("operacja", "zabieg", "protokół", "protokol", "վիրահատություն", "ოპერაცია", "əməliyyat"),
    "anesthesia_preop": ("anestezjolog", "znieczulenie", "անեսթեզիոլոգ", "ანესთეზიოლოგი", "anestezioloq"),
    "informed_consent": ("zgoda", "świadoma zgoda", "swiadoma zgoda", "համաձայնություն", "თანხმობა", "razılıq"),
    "medical_commission": ("komisja", "orzeczenie", "հանձնաժողով", "კომისია", "komissiya"),
    "lab_results": ("laboratoryjne", "wyniki badań", "լաբորատոր", "ლაბორატორიული", "laborator"),
    "instrumental_study": ("badanie obrazowe", "usg", "rtg", "tk", "mri", "հետազոտություն", "კვლევა", "müayinə"),
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
