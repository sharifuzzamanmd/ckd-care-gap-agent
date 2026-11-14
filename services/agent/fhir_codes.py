"""Codes the agent looks for in FHIR records (LOINC for labs, SNOMED for diagnoses).

Checked against 363 Synthea patients (Step 6). Real health systems use more codes;
add them here and every script picks them up.
"""

# Labs and vitals: name -> LOINC codes (any of them counts)
LABS = {
    "sbp": ["8480-6"],                 # systolic BP (a component inside the BP panel 85354-9)
    "dbp": ["8462-4"],                 # diastolic BP (also a panel component)
    "hba1c": ["4548-4"],
    "bmi": ["39156-5"],
    "hemoglobin": ["718-7"],
    "potassium": ["6298-4", "2823-3"],   # blood / serum
    "sodium": ["2947-0", "2951-2"],      # blood / serum
    "creatinine": ["38483-4", "2160-0"],  # kept for later; Synthea's values don't match its eGFR
    "egfr": ["33914-3", "62238-1", "98979-8"],  # as reported by the lab (Synthea: 33914-3)
    "uacr": ["14959-1", "9318-7"],       # urine albumin-creatinine ratio, mg/g
}
BP_PANEL = "85354-9"

# Diagnoses: SNOMED codes
DIABETES = {"44054006", "46635009"}        # type 2, type 1 (prediabetes 714628002 is NOT diabetes)
HYPERTENSION = {"59621000", "38341003"}    # essential hypertension, hypertensive disorder
KIDNEY_DISEASE = {
    "431855005", "431856006", "433144002", "431857002",  # CKD stage 1 to 4
    "46177005",            # end-stage renal disease
    "127013003",           # disorder of kidney due to diabetes
    "90781000119102",      # microalbuminuria due to type 2 diabetes
    "157141000119108",     # proteinuria due to type 2 diabetes
    "698306007",           # awaiting kidney transplant
    "161665007",           # history of kidney transplant
    "213150003",           # kidney transplant failure and rejection
}

# Every Observation code the agent needs (the loader keeps only these)
ALL_OBS_CODES = {code for codes in LABS.values() for code in codes} | {BP_PANEL}
