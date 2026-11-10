"""Score one patient with the model API, then ask Qwen to write a short clinician note."""
import re
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.agent.llm import ask

PATIENT = {"age": 67, "female": 1, "sbp": 152, "dbp": 84, "diabetes": 1,
           "told_high_bp": 1, "hba1c": 8.1, "bmi": 33, "hemoglobin": 11.9}

NAMES = {"age": "age", "female": "female", "sbp": "systolic blood pressure",
         "dbp": "diastolic blood pressure", "diabetes": "diabetes", "told_high_bp": "high blood pressure",
         "hba1c": "HbA1c", "bmi": "BMI", "hemoglobin": "hemoglobin",
         "potassium": "potassium", "sodium": "sodium"}


def numbers(text):
    return {float(n) for n in re.findall(r"\d+(?:\.\d+)?", text)}


# 1. Get the risk score and reasons from the model API
result = httpx.post("http://localhost:8000/score", json=PATIENT, timeout=60).json()
risk_pct = round(result["risk"] * 100)

# 2. Turn them into plain facts (the ONLY facts Qwen may use)
facts = [f"CKD risk score: {risk_pct}%", "Kidney tests (eGFR, UACR): not done in the past year"]
for d in result["top_drivers"]:
    if d["feature"] in ("diabetes", "told_high_bp", "female"):
        value = "yes" if d["value"] == 1 else "no"
    else:
        value = f"{d['value']:g}"  # 152.0 -> 152
    facts.append(f"{NAMES[d['feature']]}: {value} ({d['effect']})")
evidence = "\n".join(facts)

# 3. Ask Qwen to write the note
note = ask(
    "You write 2-3 sentence notes for a primary care clinician. Use ONLY the facts given. "
    "Do not add any number, diagnosis or medicine that is not in the facts. "
    "End by suggesting kidney blood (eGFR) and urine (UACR) tests.",
    f"Patient facts:\n{evidence}\n\nWrite the note.")

# 4. Safety check: every number in the note must come from the facts
invented = sorted(numbers(note) - numbers(evidence))

print("=== Facts given to Qwen ===")
print(evidence)
print("\n=== Note written by Qwen ===")
print(note)
print("\n=== Safety check ===")
print("PASSED: no invented numbers" if not invented else f"FAILED: invented numbers {invented}")