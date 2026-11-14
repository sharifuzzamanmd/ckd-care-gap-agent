"""Automatic checks for reading FHIR records and finding care gaps (Step 6)."""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.load_synthea import as_updates, slim
from services.agent.patient_facts import care_gap, model_input, patient_facts

TODAY = date(2026, 11, 14)


def patient(**extra):
    return {"resourceType": "Patient", "id": "p1", "gender": "female", "birthDate": "1960-05-01", **extra}


def lab(code, value, when, unit="mg/dL"):
    return {"resourceType": "Observation", "effectiveDateTime": f"{when}T09:00:00-05:00",
            "code": {"coding": [{"system": "http://loinc.org", "code": code}]},
            "valueQuantity": {"value": value, "unit": unit}}


def egfr(value, when, unit="mL/min/{1.73_m2}"):
    return lab("33914-3", value, when, unit)


def uacr(value, when):
    return lab("14959-1", value, when, "mg/g")


def condition(code, text):
    return {"resourceType": "Condition", "code": {"coding": [{"code": code}], "text": text}}


def bp(sbp, dbp, when):
    return {"resourceType": "Observation", "effectiveDateTime": f"{when}T09:00:00-05:00",
            "code": {"coding": [{"code": "85354-9"}]},
            "component": [{"code": {"coding": [{"code": "8480-6"}]}, "valueQuantity": {"value": sbp}},
                          {"code": {"coding": [{"code": "8462-4"}]}, "valueQuantity": {"value": dbp}}]}


def gap(resources):
    return care_gap(patient_facts(resources, TODAY), TODAY)


def test_facts_read_latest_values_and_bp_panel():
    facts = patient_facts([patient(), bp(150, 90, "2025-01-01"), bp(138, 82, "2026-06-01"),
                           lab("4548-4", 7.9, "2026-06-01", "%")], TODAY)
    assert facts["age"] == 66 and facts["female"] == 1
    assert facts["sbp"] == 138 and facts["dbp"] == 82      # latest, read from inside the BP panel
    assert facts["hba1c"] == 7.9
    assert facts["potassium"] is None                        # missing stays missing


def test_known_kidney_disease_is_not_a_gap():
    result = gap([patient(), condition("433144002", "Chronic kidney disease stage 3"), egfr(45, "2026-06-01")])
    assert result["gap"] == "kidney_diagnosis_on_record"


def test_end_stage_renal_disease_counts_as_diagnosed():
    # The old rule "name contains kidney disease" missed this one
    assert gap([patient(), condition("46177005", "End-stage renal disease")])["gap"] == "kidney_diagnosis_on_record"


def test_low_egfr_without_diagnosis_single_result_asks_for_repeat():
    result = gap([patient(), egfr(52, "2026-09-01")])
    assert result["gap"] == "lab_ckd_not_diagnosed"
    assert "repeat" in result["next_step"]


def test_low_egfr_confirmed_3_months_apart_asks_for_review():
    result = gap([patient(), egfr(55, "2026-03-01"), egfr(52, "2026-09-01")])
    assert result["gap"] == "lab_ckd_not_diagnosed"
    assert "confirmed" in result["reason"]


def test_high_uacr_without_diagnosis_is_a_gap():
    assert gap([patient(), egfr(90, "2026-09-01"), uacr(45, "2026-09-01")])["gap"] == "lab_ckd_not_diagnosed"


def test_egfr_in_wrong_unit_is_ignored():
    # Plain mL/min is not an eGFR result; it must not create a false alarm
    assert gap([patient(), egfr(8, "2026-09-01", unit="mL/min")])["gap"] == "no_gap"


def test_diabetes_without_recent_tests_is_overdue():
    result = gap([patient(), condition("44054006", "Diabetes mellitus type 2"),
                  egfr(85, "2024-01-01"), uacr(10, "2026-08-01")])
    assert result["gap"] == "kidney_tests_overdue"
    assert result["next_step"] == "order eGFR"


def test_prediabetes_is_not_diabetes():
    assert gap([patient(), condition("714628002", "Prediabetes")])["gap"] == "no_gap"


def test_diabetes_with_recent_normal_tests_has_no_gap():
    assert gap([patient(), condition("44054006", "Diabetes"), egfr(85, "2026-06-01"),
                uacr(12, "2026-06-01")])["gap"] == "no_gap"


def test_model_input_has_the_11_features():
    facts = patient_facts([patient(), condition("59621000", "Essential hypertension")], TODAY)
    inputs = model_input(facts)
    assert len(inputs) == 11 and inputs["told_high_bp"] == 1 and inputs["hba1c"] is None


def test_slim_keeps_needed_records_and_drops_broken_links():
    bundle = {"resourceType": "Bundle", "type": "transaction", "entry": [
        {"fullUrl": "urn:uuid:p", "resource": patient()},
        {"fullUrl": "urn:uuid:e", "resource": {"resourceType": "Encounter"}},
        {"fullUrl": "urn:uuid:c", "resource": {"resourceType": "Claim"}},
        {"fullUrl": "urn:uuid:o1", "resource": {**egfr(80, "2026-01-01"),
                                                "subject": {"reference": "urn:uuid:p"},
                                                "encounter": {"reference": "urn:uuid:e"}}},
        {"fullUrl": "urn:uuid:o2", "resource": lab("72514-3", 2, "2026-01-01")},  # pain score: not needed
        {"fullUrl": "urn:uuid:m", "resource": {"resourceType": "MedicationRequest",
                                               "medicationCodeableConcept": {"text": "metformin"},
                                               "reasonReference": [{"reference": "urn:uuid:c"}]}},
    ]}
    slimmed = slim(bundle)
    kept = [e["fullUrl"] for e in slimmed["entry"]]
    assert kept == ["urn:uuid:p", "urn:uuid:e", "urn:uuid:o1", "urn:uuid:m"]
    assert slimmed["entry"][2]["resource"]["encounter"] == {"reference": "urn:uuid:e"}
    assert "reasonReference" not in slimmed["entry"][3]["resource"]   # pointed at the dropped Claim


def test_reloading_updates_instead_of_duplicating():
    bundle = {"entry": [
        {"resource": {"resourceType": "Patient", "id": "abc"}, "request": {"method": "POST", "url": "Patient"}},
        {"resource": {"resourceType": "Organization", "id": "org"},
         "request": {"method": "POST", "url": "Organization", "ifNoneExist": "identifier=x|1"}},
    ]}
    requests = [e["request"] for e in as_updates(bundle)["entry"]]
    assert requests[0] == {"method": "PUT", "url": "Patient/abc"}
    assert requests[1]["method"] == "POST"     # shared records keep their own duplicate check
