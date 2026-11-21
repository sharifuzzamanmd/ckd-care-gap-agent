"""Run the agent on one patient (or the first N patients) and print what it decided."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv

load_dotenv()
from services.agent import fhir_client
from services.agent.graph import run

parser = argparse.ArgumentParser()
parser.add_argument("--patient", help="one patient ID")
parser.add_argument("--limit", type=int, default=10, help="how many patients to scan")
args = parser.parse_args()

ids = [args.patient] if args.patient else fhir_client.list_patient_ids(args.limit)
counts = {}
for pid in ids:
    r = run(pid)
    counts[r["gap"]] = counts.get(r["gap"], 0) + 1
    if r["gap"] in ("kidney_tests_overdue", "lab_ckd_not_diagnosed"):
        risk = f"{r['risk']:.0%}" if r["risk"] is not None else (r["score_missing"] or "rule-based")
        print(f"\nPatient {pid} | {r['gap']} | risk {risk}")
        print(f"  Next step: {r['next_step']}")
        print(f"  Note: {r['refused'] or r['note']}")
print(f"\nSummary: {counts}")