"""Facade парсера медицинского текста.

Реализация разложена по parse/inline/demographics/work/block mixin-модулям,
а публичный класс MedicalTextParser сохранён для старых импортов.
"""

from __future__ import annotations

import re
from typing import Dict, Sequence

from medical_parser_blocks import MedicalParserBlocksMixin
from medical_parser_core import MedicalParserCoreMixin
from medical_parser_demographics import MedicalParserDemographicsMixin
from medical_parser_inline import MedicalParserInlineMixin
from medical_parser_sanitize import sanitize_diagnosis
from medical_parser_work import MedicalParserWorkMixin


class MedicalTextParser(
    MedicalParserCoreMixin,
    MedicalParserInlineMixin,
    MedicalParserDemographicsMixin,
    MedicalParserWorkMixin,
    MedicalParserBlocksMixin,
):
    FIELD_ALIASES: Dict[str, Sequence[str]] = {
        "case_number": ("История болезни №", "История болезни N", "ИБ №", "Nr historii choroby", "Numer historii choroby", "Historia choroby nr", "Nr dokumentacji", "Numer dokumentacji", "Nr karty"),
        "fio": ("Ф.И.О.", "Ф.И.О", "ФИО", "ФИО пациента", "Ф.И.О. пациента", "Ф.И.О пациента", "Фамилия Имя Отчество", "Пациент", "Пациентка", "Больной", "Больная", "Pacjent", "Pacjentka", "Imię i nazwisko", "Imie i nazwisko", "Nazwisko i imię", "Nazwisko i imie"),
        "birth": ("Год рождения", "Дата рождения", "г.р.", "Возраст", "Data urodzenia", "Urodzony", "Urodzona", "Wiek"),
        "registered": ("Зарегистрирован", "зарегистрирован по адресу", "Проживает", "Место жительства", "Адрес проживания", "Адрес места жительства", "Адрес регистрации", "Adres", "Adres zamieszkania", "Miejsce zamieszkania"),
        "psych_account": ("На учёте у психиатров", "На учете у психиатров"),
        "work_org": ("Работает в организации", "Работает", "Место работы", "Работа", "Miejsce pracy", "Pracuje", "Zakład pracy", "Zaklad pracy"),
        "position": ("Должность", "Stanowisko", "Zawód", "Zawod"),
        "sick_leave": ("Больничный лист", "ЛН", "Лист нетрудоспособности"),
        "disability": ("Оформление инвалидности", "Инвалидность"),
        "rvk_referral": ("Направление от РВК", "РВК"),
        "admission": ("Поступает", "Поступил", "Поступила", "Госпитализирован", "Госпитализирована", "Przyjęty", "Przyjety", "Przyjęta", "Przyjeta", "Hospitalizowany", "Hospitalizowana"),
        "doctor": ("Лечащий врач", "Врач", "Врач психиатр", "Врач-психиатр", "Хирург", "Терапевт", "Lekarz", "Lekarz prowadzący", "Lekarz prowadzacy", "Chirurg", "Terapeuta"),
        "head": ("Заведующий отделением", "Зав. отделением", "Зав. отд.", "Зав отд", "Зав.отделением", "Ordynator", "Kierownik oddziału", "Kierownik oddzialu"),
    }

    BLOCK_ALIASES: Dict[str, Sequence[str]] = {
        "complaints": ("Жалобы на момент осмотра", "Жалобы при поступлении", "Жалобы", "Skargi", "Dolegliwości", "Dolegliwosci", "Skargi przy przyjęciu", "Skargi przy przyjeciu"),
        "life_anamnesis": ("Анамнез жизни", "Wywiad życiowy", "Wywiad zyciowy", "Wywiad osobniczy"),
        "disease_anamnesis": ("Анамнез заболевания", "Wywiad chorobowy", "Wywiad obecnej choroby", "Historia choroby"),
        "mental_status": ("Профильный статус при поступлении", "Профильный статус", "Психический статус при поступлении", "Психический статус", "Stan psychiczny", "Badanie psychiatryczne"),
        "somatic_status": ("Сомато-неврологический статус", "Соматический статус", "Объективный статус", "Объективно", "Status praesens", "Stan przedmiotowy", "Badanie przedmiotowe", "Stan somatyczny"),
        "examination_plan": ("План обследования", "Plan badań", "Plan badan"),
        "treatment_plan": ("План лечения", "Назначенное лечение", "Лечение", "Plan leczenia", "Zalecone leczenie", "Zastosowane leczenie", "Leczenie", "Terapia"),
        "diagnosis": ("Клинический диагноз", "Предварительный диагноз", "Основной диагноз", "Заключительный диагноз", "Диагноз", "был выставлен диагноз", "установлен диагноз", "выставлен диагноз", "Rozpoznanie kliniczne", "Rozpoznanie główne", "Rozpoznanie glowne", "Rozpoznanie", "Diagnoza"),
        "epidemiology": ("Эпидемиологический анамнез", "Wywiad epidemiologiczny"),
    }

    SECTION_MARKERS: Sequence[str] = (
        "Дата, время",
        "Дата поступления",
        "Дата госпитализации",
        "Дата приема",
        "Дата приёма",
        "Дата осмотра",
        "Дата выписки",
        "История болезни №",
        "Ф.И.О.",
        "Ф.И.О",
        "ФИО",
        "ФИО пациента",
        "Ф.И.О. пациента",
        "Год рождения",
        "Дата рождения",
        "Возраст",
        "Зарегистрирован",
        "Проживает",
        "Место жительства",
        "Адрес проживания",
        "Адрес места жительства",
        "На учёте у психиатров",
        "На учете у психиатров",
        "Работает в организации",
        "Место работы",
        "Должность",
        "Больничный лист",
        "Оформление инвалидности",
        "Направление от РВК",
        "Поступает",
        "Поступил",
        "Поступила",
        "Госпитализирован",
        "Госпитализирована",
        "В 3 отделение КДП поступает",
        "Жалобы на момент осмотра",
        "Жалобы при поступлении",
        "Жалобы",
        "Анамнез жизни",
        "Анамнез заболевания",
        "Профильный статус при поступлении",
        "Профильный статус",
        "Психический статус при поступлении",
        "Психический статус",
        "Сомато-неврологический статус",
        "Соматический статус",
        "План обследования",
        "План лечения",
        "Назначенное лечение",
        "На основании данных",
        "Клинический диагноз",
        "Предварительный диагноз",
        "Основной диагноз",
        "Заключительный диагноз",
        "Диагноз",
        "Эпидемиологический анамнез",
        "Результаты обследований",
        "Результаты исследований",
        "ЭЭГ",
        "ЭПИ",
        "За время лечения",
        "Рекомендовано",
        "Лечение",
        "Экспертный анамнез",
        "Лечащий врач",
        "Врач",
        "Врач психиатр",
        "Врач-психиатр",
        "Заведующий отделением",
        "Зав. отделением",
        "Зав. отд.",
        "Зав отд",
        "Karta informacyjna leczenia szpitalnego",
        "Historia choroby",
        "Dokumentacja medyczna",
        "Pacjent",
        "Pacjentka",
        "Imię i nazwisko",
        "Imie i nazwisko",
        "Data urodzenia",
        "Nr historii choroby",
        "Numer historii choroby",
        "Data przyjęcia",
        "Data przyjecia",
        "Data hospitalizacji",
        "Data wypisu",
        "Skargi",
        "Dolegliwości",
        "Dolegliwosci",
        "Wywiad chorobowy",
        "Wywiad życiowy",
        "Wywiad zyciowy",
        "Stan psychiczny",
        "Stan somatyczny",
        "Stan przedmiotowy",
        "Plan badań",
        "Plan badan",
        "Plan leczenia",
        "Zalecone leczenie",
        "Zastosowane leczenie",
        "Leczenie",
        "Rozpoznanie kliniczne",
        "Rozpoznanie główne",
        "Rozpoznanie glowne",
        "Rozpoznanie",
        "Wyniki badań",
        "Wyniki badan",
        "Zalecenia",
        "Lekarz",
        "Lekarz prowadzący",
        "Lekarz prowadzacy",
        "Ordynator",
        "Kierownik oddziału",
        "Kierownik oddzialu",
    )

    LIFE_ANAMNESIS_START_RE = re.compile(
        r"(?i)(?<![А-Яа-яA-Za-z0-9])("
        r"наследственность|рождение\s+в\s+городе|родил(?:ся|ась)?\s+в|"
        r"на\s+момент\s+рождения\s+семья|в\s+настоящее\s+время\s+семья|"
        r"братья\s*/\s*с[её]стры|братьев|с[её]ст[её]р|"
        r"беременность\s*/\s*роды|беременность\s+и\s+роды|"
        r"дду|общение\s+в\s+дду|общеобразовательн\w*\s+школ\w*|"
        r"коррекционн\w*\s+школ\w*|во\s+время\s+уч[её]бы|"
        r"после\s+школы|специальность|окончание\s+уч[её]бы|"
        r"в\s+настоящее\s+время\s+работа|брак|дети|проживает\s*[-:])"
    )

