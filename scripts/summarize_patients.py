"""Check the synthetic patients: who has a kidney care gap, and what data each has.

Reads patients from the FHIR server (default) or straight from Synthea files.

    python scripts/summarize_patients.py                    # from http://localhost:8080/fhir
    python scripts/summarize_patients.py --files synthea/output/fhir
    python scripts/summarize_patients.py --score            # also ask the model API to rank untested patients
"""
import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.agent.patient_facts import care_gap, model_input, patient_facts


def from_files(folder):
    """Yield each patient's resources from Synthea bundle files."""
    for f in sorted(Path(folder).glob("*.json")):
        if f.name.startswith(("hospitalInformation", "practitionerInformation")):
            continue
        yield [e["resource"] for e in json.loads(f.read_bytes())["entry"]]


def _pages(client, url):
    """Follow FHIR paging links and yield every resource."""
    while url:
        page = client.get(url).raise_for_status().json()
        yield from (e["resource"] for e in page.get("entry", []))
        url = next((link["url"] for link in page.get("link", []) if link["relation"] == "next"), None)


def from_server(fhir):
    """Yield each patient's resources from the FHIR server."""
    with httpx.Client(timeout=120) as client:
        patient_ids = [p["id"] for p in _pages(client, f"{fhir}/Patient?_elements=id&_count=500")]
        for pid in patient_ids:
            yield list(_pages(client, f"{fhir}/Patient/{pid}/$everything?_count=1000"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fhir", default="http://localhost:8080/fhir")
    parser.add_argument("--files", help="read Synthea bundles from this folder instead of the server")
    parser.add_argument("--score", action="store_true", help="score untested patients with the model API")
    parser.add_argument("--model-api", default="http://localhost:8000")
    args = parser.parse_args()

    today = date.today()
    source = from_files(args.files) if args.files else from_server(args.fhir)
    rows = []
    for resources in source:
        facts = patient_facts(resources, today)
        if not facts["deceased"]:
            rows.append((facts, care_gap(facts, today)))

    gaps = Counter(gap["gap"] for _, gap in rows)
    print(f"Living patients: {len(rows)}")
    for name in ["kidney_diagnosis_on_record", "lab_ckd_not_diagnosed", "kidney_tests_overdue", "no_gap"]:
        print(f"  {name:28s} {gaps[name]:4d}  ({gaps[name] / max(len(rows), 1):.0%})")

    print("\nShare of living patients with each model input:")
    for name in ["sbp", "hba1c", "bmi", "hemoglobin", "potassium", "sodium"]:
        have = sum(f[name] is not None for f, _ in rows)
        print(f"  {name:12s} {have / max(len(rows), 1):.0%}")

    print("\nExamples:")
    for name in ["lab_ckd_not_diagnosed", "kidney_tests_overdue"]:
        for facts, gap in [r for r in rows if r[1]["gap"] == name][:3]:
            print(f"  {facts['patient_id'][:8]}  age {facts['age']}  {name}: {gap['reason']} -> {gap['next_step']}")

    if args.score:
        untested = [f for f, g in rows if g["gap"] == "kidney_tests_overdue"]
        with httpx.Client(timeout=60) as client:
            scored = sorted(((client.post(f"{args.model_api}/score", json=model_input(f)).raise_for_status().json(), f)
                             for f in untested), key=lambda t: -t[0]["risk"])
        print(f"\nModel ranking of {len(scored)} patients with overdue kidney tests (top 5):")
        for result, facts in scored[:5]:
            reasons = ", ".join(d["feature"] for d in result["top_drivers"][:3])
            print(f"  {facts['patient_id'][:8]}  age {facts['age']}  risk {result['risk']:.2f}  "
                  f"flag {result['flag']}  top reasons: {reasons}")


if __name__ == "__main__":
    main()
