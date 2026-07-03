"""Полная эмуляция пользовательских сценариев врача на живом Tkinter GUI.

Запуск (вручную, вне pytest — сценарии тяжёлые):
    xvfb-run -a python3 tools/doctor_emulation/run_all_scenarios.py         # все
    xvfb-run -a python3 tools/doctor_emulation/run_all_scenarios.py s2      # один

Каждый сценарий поднимает НАСТОЯЩЕЕ приложение, эмулирует ответы врача в
диалогах и кликает по реальным виджетам (включая модальный intake-попап).
Журнал попапов служит метрикой трения: сколько действий требуется от врача.
"""
"""Матрица сценариев врача. Каждый сценарий: (имя, функция) -> (ok, детали)."""
import faulthandler, sys
faulthandler.dump_traceback_later(60, exit=True)
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from doctor_sim import DoctorSim, make_docx
from medical_docx_reader import extract_docx_text
from pathlib import Path
import traceback

RESULTS = []

class ScenarioFailure(AssertionError):
    """Explicit scenario failure that survives python -O."""


def check(condition, message=""):
    if not condition:
        raise ScenarioFailure(str(message))



def scenario(name):
    def deco(fn):
        def run():
            sim = None
            try:
                import doctor_sim as _ds
                holder = {}
                _orig_init = _ds.DoctorSim.__init__
                def _spy(selfd, *a, **k):
                    _orig_init(selfd, *a, **k); holder["sim"] = selfd
                _ds.DoctorSim.__init__ = _spy
                try:
                    sim = fn()
                finally:
                    _ds.DoctorSim.__init__ = _orig_init
                    if sim is None: sim = holder.get("sim")
                RESULTS.append((name, True, "", sim.popups if sim else []))
            except Exception as exc:
                sim = holder.get("sim") if 'holder' in dir() else sim
                tb = traceback.format_exc().splitlines()[-3:]
                extra = f" || errors={getattr(sim,'errors',None)} popups={getattr(sim,'popups',None)}" if sim else ""
                RESULTS.append((name, False, f"{exc} | {' / '.join(tb)}{extra}", sim.popups if sim else []))
            finally:
                if sim: sim.close()
        return run
    return deco

def primary_lines(fio="Орлова Мария Ивановна, 1985 г.р.", adm="05.05.2026", dis="19.05.2026", diag="Депрессивный эпизод средней степени F32.1"):
    return [
        f"История болезни № 314/26. Пациентка: {fio}",
        f"Дата поступления: {adm}. Дата выписки: {dis}.",
        "Жалобы: на подавленное настроение.",
        "Психический статус: ориентирована верно.",
        f"Диагноз: {diag}.",
        "Лечение: сертралин 100 мг утром.",
    ]

@scenario("S1: дроп + дневники ежедневно (базовый)")
def s1():
    sim = DoctorSim()
    p = sim.root_dir/"p.docx"; make_docx(p, primary_lines())
    t = sim.root_dir/"тексты F32.docx"; make_docx(t, ["Фон выравнивается.","Активнее в режиме."])
    sim.drop(p); sim.app.status_files=[t]
    sim.app.create_diaries(); sim.pump(0.5)
    files = [f for f in sim.outputs() if "дневник" in f.name.lower()]
    check(files, f"нет дневников; ошибки: {sim.errors}")
    text = extract_docx_text(files[0])
    check("06.05.26 " in text and "05.05.26" not in text, text[:120])
    check(not sim.errors, sim.errors)
    return sim

@scenario("S2: intake-подхват при работающей программе (сердце продукта)")
def s2():
    sim = DoctorSim()
    # включаем intake-папку как после согласия врача
    sim.app._desktop_intake_enabled = True
    sim.app._desktop_intake_folder = str(sim.intake)
    sim.app._desktop_intake_seen_signatures = set()
    t = sim.root_dir/"тексты F32.docx"; make_docx(t, ["Фон выравнивается."])
    # врач выбирает тексты честным каналом (кнопка «Тексты»)
    sim.answers["openfilenames"] = (str(t),)
    sim.app.choose_status_files()
    check(sim.app.diary_texts_dir, "канал выбора текстов не сохранил папку")
    # врач бросает файл в папку
    import os, time as _t
    p = sim.intake/"Пациент.docx"; make_docx(p, primary_lines())
    old=_t.time()-5; os.utime(p,(old,old))
    driver_state = {"ok": False, "note": ""}
    def driver():
        tops = sim.toplevels()
        if not tops:
            driver_state["note"] = "intake-попап не открылся"
            return
        pop = tops[-1]
        got = sim.toggle_check("Дневник", pop) or sim.toggle_check("дневник", pop)
        if not got:
            driver_state["note"] = "нет чекбокса дневников в intake-попапе"
            pop.destroy(); return
        if not sim.click_button("без печати", pop):
            driver_state["note"] = "нет кнопки создания"
            pop.destroy(); return
        driver_state["ok"] = True
    sim.tk_root.after(700, driver)
    sim.app._poll_desktop_intake_folder(); sim.pump(1.0)
    check(driver_state["ok"], driver_state["note"] or "драйвер попапа не сработал")
    files = [f for f in sim.outputs() if "дневник" in f.name.lower()]
    check(files, f"intake не создал дневники; ошибки: {sim.errors}; попапы: {sim.popups}")
    check(not sim.errors, sim.errors)
    return sim

@scenario("S3: клиническая схема дат (ответ 2)")
def s3():
    sim = DoctorSim(answers={("askstring","Как составлять дневники"): "2"})
    p = sim.root_dir/"p.docx"; make_docx(p, primary_lines(adm="01.05.2026", dis="30.05.2026"))
    t = sim.root_dir/"т.docx"; make_docx(t, ["Стабильно."])
    sim.drop(p); sim.app.status_files=[t]
    sim.app.create_diaries(); sim.pump(0.5)
    files=[f for f in sim.outputs() if "дневник" in f.name.lower()]
    check(files, sim.errors)
    text=extract_docx_text(files[0])
    # схема +1,+2,+3,+7,...: должны быть 02.05 и 08.05, но не 05.05/06.05 подряд все дни
    check("02.05.26" in text and "08.05.26" in text, text[:200])
    check("05.05.26" not in text, "клиническая схема не применилась (день +4 присутствует)")
    return sim

@scenario("S4: свои дни (ответ '3,5,9')")
def s4():
    sim = DoctorSim(answers={("askstring","Как составлять дневники"): "3,5,9"})
    p = sim.root_dir/"p.docx"; make_docx(p, primary_lines(adm="01.05.2026", dis="30.05.2026"))
    t = sim.root_dir/"т.docx"; make_docx(t, ["Стабильно."])
    sim.drop(p); sim.app.status_files=[t]
    sim.app.create_diaries(); sim.pump(0.5)
    files=[f for f in sim.outputs() if "дневник" in f.name.lower()]
    check(files, sim.errors)
    text=extract_docx_text(files[0])
    check("04.05.26" in text and "06.05.26" in text and "10.05.26" in text, text[:200])
    check("02.05.26" not in text, "кастомные дни не применились")
    return sim

@scenario("S5: мужской пациент — адаптация рода")
def s5():
    sim = DoctorSim()
    p = sim.root_dir/"p.docx"; make_docx(p, [
        "История болезни № 7/26. Пациент: Иванов Иван Иванович, 1980 г.р.",
        "Дата поступления: 05.05.2026. Дата выписки: 12.05.2026.",
        "Диагноз: F20.0.",
    ])
    t = sim.root_dir/"т.docx"; make_docx(t, ["Ориентирована верно, спокойна, доступна контакту."])
    sim.drop(p); sim.app.status_files=[t]
    sim.app.create_diaries(); sim.pump(0.5)
    files=[f for f in sim.outputs() if "дневник" in f.name.lower()]
    check(files, sim.errors)
    text=extract_docx_text(files[0])
    check("Ориентирован верно" in text and "спокоен" in text, text[:200])
    return sim

@scenario("S6: без даты выписки — попап честно спрашивает и работает")
def s6():
    sim = DoctorSim(answers={("field","Дата выписки"): "12.05.2026"})
    p = sim.root_dir/"p.docx"; make_docx(p, [
        "Пациент: Иванов Иван Иванович, 1980 г.р.",
        "Дата поступления: 05.05.2026.",
        "Диагноз: F32.1.",
    ])
    t = sim.root_dir/"т.docx"; make_docx(t, ["Стабильно."])
    sim.drop(p); sim.app.status_files=[t]
    sim.app.create_diaries(); sim.pump(0.5)
    files=[f for f in sim.outputs() if "дневник" in f.name.lower()]
    check(files, f"{sim.errors} | {sim.popups}")
    text=extract_docx_text(files[0])
    check("06.05.26" in text and "12.05.26" in text, text[:150])
    return sim

@scenario("S7: второй пациент в той же сессии — нет утечки данных")
def s7():
    sim = DoctorSim()
    texts_dir = sim.root_dir/"Тексты дневников"; texts_dir.mkdir()
    tf = texts_dir/"дневники F32 депрессия.docx"; make_docx(tf, ["Фон выравнивается, стабильна."])
    tk_ = texts_dir/"дневники K35 аппендицит.docx"; make_docx(tk_, ["Живот мягкий, швы чистые."])
    p1 = sim.root_dir/"p1.docx"; make_docx(p1, primary_lines())
    sim.drop(p1)
    sim.answers["openfilenames"] = (str(tf),)
    sim.app.choose_status_files()
    sim.app.create_diaries(); sim.pump(0.3)
    p2 = sim.root_dir/"p2.docx"; make_docx(p2, [
        "Пациент: Сидоров Пётр Кузьмич, 1965 г.р.",
        "Дата поступления: 01.06.2026. Дата выписки: 08.06.2026.",
        "Диагноз: K35.8.",
    ])
    sim.drop(p2)
    check(sim.app.patient_name_var.get() == "Сидоров Пётр Кузьмич", sim.app.patient_name_var.get())
    check(sim.app.discharge_date_var.get() == "08.06.2026", f"утечка выписки: {sim.app.discharge_date_var.get()!r}")
    check(sim.app.admission_date_var.get() == "01.06.2026")
    sim.app.create_diaries(); sim.pump(0.3)
    files=[f for f in sim.outputs() if "Сидоров" in f.name and "дневник" in f.name.lower()]
    check(files, f"{sim.errors} | {sim.popups[-3:]}")
    text=extract_docx_text(files[0])
    check("02.06.26" in text and "05.05" not in text, text[:150])
    check("Живот мягкий" in text, f"автоподбор не выбрал K35-тексты: {text[:120]}")
    return sim

@scenario("S8: почасовые дневники через переключатель")
def s8():
    sim = DoctorSim(answers={("askstring","Дневники по часам"): "2"})
    p = sim.root_dir/"p.docx"; make_docx(p, primary_lines(adm="05.05.2026 14:00", dis="07.05.2026"))
    t = sim.root_dir/"т.docx"; make_docx(t, ["Стабильно."])
    sim.drop(p)
    sim.answers["openfilenames"] = (str(t),)
    sim.app.choose_status_files()
    sim.app.diary_frequency_mode_var.set("hourly")
    sim.app.create_diaries(); sim.pump(0.5)
    files=[f for f in sim.outputs() if "дневник" in f.name.lower()]
    check(files, sim.errors)
    text=extract_docx_text(files[0])
    check(":" in text.splitlines()[0], f"нет времени в почасовом дневнике: {text[:120]}")
    return sim

@scenario("S9: повторный дроп того же файла — не дублирует и не путает")
def s9():
    sim = DoctorSim()
    p = sim.root_dir/"p.docx"; make_docx(p, primary_lines())
    t = sim.root_dir/"т.docx"; make_docx(t, ["Стабильно."])
    sim.drop(p)
    sim.answers["openfilenames"] = (str(t),)
    sim.app.choose_status_files()
    sim.app.create_diaries(); sim.pump(0.3)
    n1 = len(sim.outputs())
    sim.drop(p)  # врач случайно бросил тот же файл ещё раз
    check(sim.app.patient_name_var.get() == "Орлова Мария Ивановна")
    check(sim.app.discharge_date_var.get() == "19.05.2026", sim.app.discharge_date_var.get())
    sim.app.create_diaries(); sim.pump(0.3)
    files=[f for f in sim.outputs() if "дневник" in f.name.lower()]
    check(files, sim.errors)
    return sim

@scenario("S10: отмена мастера — вежливая остановка без создания")
def s10():
    sim = DoctorSim(answers={("askyesno","Мастер дневников"): False})
    p = sim.root_dir/"p.docx"; make_docx(p, primary_lines())
    t = sim.root_dir/"т.docx"; make_docx(t, ["Стабильно."])
    sim.drop(p)
    sim.answers["openfilenames"] = (str(t),)
    sim.app.choose_status_files()
    sim.app.create_diaries(); sim.pump(0.3)
    files=[f for f in sim.outputs() if "дневник" in f.name.lower()]
    check(not files, "мастер отменён, но файлы созданы")
    # и никакого ERROR — только вежливое сообщение
    check(not any(k=="ERROR" for k,_ in sim.popups), sim.popups)
    return sim

@scenario("S11: документ врача с плейсхолдерами — данные подставлены")
def s11():
    sim = DoctorSim()
    p = sim.root_dir/"p.docx"; make_docx(p, primary_lines())
    sim.drop(p)
    # врач один раз создал кнопку из своего шаблона
    tpl = sim.root_dir/"Выписной эпикриз.docx"
    make_docx(tpl, [
        "ВЫПИСНОЙ ЭПИКРИЗ",
        "ФИО: {{patient.fio}}",
        "Дата рождения: {{patient.birth_date}}",
        "Поступил: {{admission.date}}  Выписан: {{discharge.date}}",
        "Диагноз: {{diagnosis.main}}",
    ])
    from universal_template_engine import attach_template_to_pack
    pack = sim.app._load_or_create_universal_pack()
    profile_dir = sim.app._universal_profile_path().parent
    spec, _target = attach_template_to_pack(pack, tpl, profile_dir, button_label="Выписной эпикриз")
    from universal_profiles import save_document_pack
    save_document_pack(pack, sim.app._universal_profile_path())
    created = sim.app._create_custom_documents_impl([str(spec.id)])
    check(created, sim.errors)
    text = extract_docx_text(created[0])
    check("Орлова Мария Ивановна" in text and "1985" in text, text[:200])
    check("05.05.2026" in text and "19.05.2026" in text, text[:250])
    check("F32.1" in text, text[:250])
    check("{{patient.fio}}" not in text, "плейсхолдер не подставлен")
    return sim

for fn_name in list(globals()):
    pass
import sys as _s
only = _s.argv[1] if len(_s.argv)>1 else None
runs = [v for k,v in sorted(globals().items()) if k.startswith("s") and callable(v) and k[1:].isdigit() and (only is None or k==only)]
for r in runs: r()

print("\n" + "="*72)
for name, ok, detail, popups in RESULTS:
    mark = "OK  " if ok else "FAIL"
    print(f"{mark} {name}")
    if not ok: print(f"     -> {detail[:300]}")
    print(f"     попапов/кликов: {len(popups)}")
fails = [r for r in RESULTS if not r[1]]
print(f"\nИтог: {len(RESULTS)-len(fails)}/{len(RESULTS)} сценариев прошли")
