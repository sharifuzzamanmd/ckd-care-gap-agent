"""Read patients from the FHIR server (same approach as scripts/summarize_patients.py)."""
import os

import httpx

FHIR_URL = os.getenv("FHIR_URL", "http://localhost:8080/fhir")


def _pages(client, url):
    """Follow FHIR paging and yield every resource."""
    while url:
        r = client.get(url)
        r.raise_for_status()
        bundle = r.json()
        for entry in bundle.get("entry", []):
            yield entry["resource"]
        url = next((l["url"] for l in bundle.get("link", []) if l["relation"] == "next"), None)


def list_patient_ids(limit: int = 1000) -> list[str]:
    with httpx.Client(timeout=120) as client:
        ids = [r["id"] for r in _pages(client, f"{FHIR_URL}/Patient?_elements=id&_count=500")]
    return ids[:limit]


def patient_resources(patient_id: str) -> list[dict]:
    """All records for one patient: Patient, Conditions, Observations, ..."""
    with httpx.Client(timeout=120) as client:
        return list(_pages(client, f"{FHIR_URL}/Patient/{patient_id}/$everything?_count=1000"))