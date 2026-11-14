"""Turn one patient's FHIR resources into plain facts and a care-gap decision.

Pure functions (no network), so they are easy to test. The agent (Step 8) will use
the same functions on records it fetches from the FHIR server.
"""
from datetime import date, datetime

from services.agent.fhir_codes import BP_PANEL, DIABETES, HYPERTENSION, KIDNEY_DISEASE, LABS

MODEL_FEATURES = ["age", "female", "sbp", "dbp", "diabetes", "told_high_bp",
                  "hba1c", "bmi", "hemoglobin", "potassium", "sodium"]
REPEAT_DAYS = 90       # CKD needs abnormal results at least 3 months apart
TEST_WINDOW_DAYS = 365  # kidney tests expected once a year for diabetes / high BP


def _day(text):
    return datetime.fromisoformat(text[:10]).date()


def _age(birth, on):
    return on.year - birth.year - ((on.month, on.day) < (birth.month, birth.day))


def _codes(resource):
    return {c.get("code") for c in resource.get("code", {}).get("coding", [])}


def lab_results(resources):
    """All lab and vital results as {name: [(date, value), ...]}, oldest first."""
    code_to_name = {code: name for name, codes in LABS.items() for code in codes}
    results = {name: [] for name in LABS}
    for r in resources:
        if r.get("resourceType") != "Observation" or "effectiveDateTime" not in r:
            continue
        when = _day(r["effectiveDateTime"])
        parts = [r] + (r.get("component", []) if BP_PANEL in _codes(r) else [])
        for part in parts:
            quantity = part.get("valueQuantity", {})
            if quantity.get("value") is None:
                continue
            for code in _codes(part):
                name = code_to_name.get(code)
                # eGFR must be reported per 1.73 m2; a plain mL/min value is a different measure
                if name == "egfr" and "1.73" not in quantity.get("unit", ""):
                    continue
                if name:
                    results[name].append((when, float(quantity["value"])))
    for name in results:
        results[name].sort()
    return results


def diagnoses(resources):
    """Which conditions are on record (ever recorded counts as known)."""
    found = {"diabetes": False, "high_bp": False, "kidney_disease": []}
    for r in resources:
        if r.get("resourceType") != "Condition":
            continue
        codes = _codes(r)
        found["diabetes"] |= bool(codes & DIABETES)
        found["high_bp"] |= bool(codes & HYPERTENSION)
        if codes & KIDNEY_DISEASE:
            found["kidney_disease"].append(r.get("code", {}).get("text", "kidney disease"))
    return found


def patient_facts(resources, today=None):
    """Plain facts about one patient from their FHIR resources."""
    today = today or date.today()
    patient = next(r for r in resources if r.get("resourceType") == "Patient")
    birth = _day(patient["birthDate"])
    female = patient.get("gender") == "female"
    labs = lab_results(resources)
    dx = diagnoses(resources)

    def latest(name):
        return labs[name][-1] if labs[name] else (None, None)

    facts = {
        "patient_id": patient.get("id"),
        "deceased": "deceasedDateTime" in patient or patient.get("deceasedBoolean", False),
        "age": _age(birth, today),
        "female": int(female),
        "diabetes": int(dx["diabetes"]),
        "told_high_bp": int(dx["high_bp"]),
        "kidney_diagnoses": sorted(set(dx["kidney_disease"])),
        "egfr_history": labs["egfr"],
        "uacr_history": labs["uacr"],
    }
    for name in ["sbp", "dbp", "hba1c", "bmi", "hemoglobin", "potassium", "sodium"]:
        when, value = latest(name)
        facts[name] = value
        facts[f"{name}_date"] = when
    return facts


def _abnormal(history, is_abnormal):
    """(latest result abnormal?, confirmed by an earlier abnormal result 90+ days before?)"""
    if not history or not is_abnormal(history[-1][1]):
        return False, False
    last_day = history[-1][0]
    confirmed = any(is_abnormal(v) and (last_day - d).days >= REPEAT_DAYS for d, v in history[:-1])
    return True, confirmed


def care_gap(facts, today=None):
    """Decide the care gap for one patient.

    Returns {"gap": ..., "reason": ..., "next_step": ...}. Gaps, checked in this order:
      kidney_diagnosis_on_record  already diagnosed; outside this tool's scope
      lab_ckd_not_diagnosed       kidney labs show CKD but no diagnosis is recorded
      kidney_tests_overdue        diabetes or high BP without eGFR and UACR in the past year
      no_gap
    """
    today = today or date.today()
    if facts["kidney_diagnoses"]:
        return {"gap": "kidney_diagnosis_on_record", "reason": facts["kidney_diagnoses"][0],
                "next_step": "none (managed as known kidney disease)"}

    low_egfr, egfr_confirmed = _abnormal(facts["egfr_history"], lambda v: v < 60)
    high_uacr, uacr_confirmed = _abnormal(facts["uacr_history"], lambda v: v >= 30)
    if low_egfr or high_uacr:
        reasons = []
        if low_egfr:
            reasons.append(f"latest eGFR {facts['egfr_history'][-1][1]:g}")
        if high_uacr:
            reasons.append(f"latest UACR {facts['uacr_history'][-1][1]:g} mg/g")
        if egfr_confirmed or uacr_confirmed:
            return {"gap": "lab_ckd_not_diagnosed", "reason": ", ".join(reasons) + " (confirmed 90+ days apart)",
                    "next_step": "review for CKD diagnosis"}
        return {"gap": "lab_ckd_not_diagnosed", "reason": ", ".join(reasons) + " (single result)",
                "next_step": "repeat eGFR and UACR in 3 months to confirm"}

    if facts["diabetes"] or facts["told_high_bp"]:
        def recent(history):
            return bool(history) and (today - history[-1][0]).days <= TEST_WINDOW_DAYS
        missing = [name for name, history in [("eGFR", facts["egfr_history"]), ("UACR", facts["uacr_history"])]
                   if not recent(history)]
        if missing:
            risk = "diabetes" if facts["diabetes"] else "high blood pressure"
            return {"gap": "kidney_tests_overdue", "reason": f"{risk}; no {' or '.join(missing)} in the past year",
                    "next_step": f"order {' and '.join(missing)}"}

    return {"gap": "no_gap", "reason": "", "next_step": "none"}


def model_input(facts):
    """The 11 inputs the model API (/score) expects. Missing values stay None."""
    return {name: facts[name] for name in MODEL_FEATURES}
