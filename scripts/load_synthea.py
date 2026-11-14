"""Upload Synthea FHIR bundles to the local HAPI FHIR server.

Synthea writes ~6 MB per patient (claims, billing, imaging...). The agent only needs
patients, visits, diagnoses, medicines and a few labs, so by default each bundle is
slimmed first, which makes loading about 10x faster. Use --full to upload everything.

    python scripts/load_synthea.py              # all patients, slimmed
    python scripts/load_synthea.py --limit 20   # quick test with 20 patients

Safe to run again: each record is saved under its own Synthea id (PUT), so a rerun
updates records instead of creating duplicates.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.agent.fhir_codes import ALL_OBS_CODES

KEEP_TYPES = {"Patient", "Encounter", "Condition", "Observation", "MedicationRequest"}


def keep(resource):
    kind = resource["resourceType"]
    if kind not in KEEP_TYPES:
        return False
    if kind == "Observation":
        return any(c.get("code") in ALL_OBS_CODES for c in resource.get("code", {}).get("coding", []))
    if kind == "MedicationRequest":
        return "medicationCodeableConcept" in resource  # skip ones pointing to a separate Medication
    return True


def _drop_dangling(value, kept):
    """Remove links to resources that were dropped, so the server can resolve every link."""
    if isinstance(value, dict):
        ref = value.get("reference", "")
        if ref.startswith("urn:uuid:") and ref not in kept:
            return None
        cleaned = {}
        for k, v in value.items():
            v = _drop_dangling(v, kept)
            if v is not None and v != []:
                cleaned[k] = v
        return cleaned
    if isinstance(value, list):
        return [x for x in (_drop_dangling(v, kept) for v in value) if x is not None]
    return value


def slim(bundle):
    """Keep only what the agent needs; drop links to removed resources."""
    entries = [e for e in bundle["entry"] if keep(e["resource"])]
    kept = {e["fullUrl"] for e in entries}
    return {**bundle, "entry": [_drop_dangling(e, kept) for e in entries]}


def as_updates(bundle):
    """Save each record under its Synthea id (PUT), so loading twice creates no duplicates."""
    for e in bundle["entry"]:
        r = e["resource"]
        if e["request"]["method"] == "POST" and "ifNoneExist" not in e["request"] and r.get("id"):
            e["request"] = {"method": "PUT", "url": f"{r['resourceType']}/{r['id']}"}
    return bundle


def wait_for_server(client, fhir, minutes=5):
    """The server takes a minute or two to start; wait until it answers."""
    for _ in range(minutes * 12):
        try:
            if client.get(f"{fhir}/metadata").status_code == 200:
                return
        except httpx.TransportError:
            pass
        print("Waiting for the FHIR server to start...")
        time.sleep(5)
    sys.exit(f"FHIR server at {fhir} did not answer. Is it running? (docker ps)")


def post(client, fhir, bundle, tries=3):
    """Send one bundle; if the connection drops, wait for the server and try again."""
    for attempt in range(1, tries + 1):
        try:
            return client.post(fhir, json=bundle, headers={"Content-Type": "application/fhir+json"})
        except httpx.TransportError as error:
            if attempt == tries:
                raise
            print(f"  connection problem ({error.__class__.__name__}); retrying...")
            wait_for_server(client, fhir)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fhir", default="http://localhost:8080/fhir")
    parser.add_argument("--folder", default="synthea/output/fhir")
    parser.add_argument("--limit", type=int, help="load only this many patients")
    parser.add_argument("--full", action="store_true", help="upload bundles unchanged")
    args = parser.parse_args()

    files = sorted(Path(args.folder).glob("*.json"))
    # Hospitals and practitioners must be loaded before the patients that reference them.
    first = [f for f in files if f.name.startswith(("hospitalInformation", "practitionerInformation"))]
    patients = [f for f in files if f not in first][: args.limit]
    if not files:
        sys.exit(f"No bundles in {args.folder}. Run Synthea first.")

    failed = 0
    start = time.time()
    with httpx.Client(timeout=600) as client:
        wait_for_server(client, args.fhir)
        for i, f in enumerate(first + patients, 1):
            bundle = json.loads(f.read_bytes())
            if f in patients:
                bundle = as_updates(bundle if args.full else slim(bundle))
            r = post(client, args.fhir, bundle)
            ok = r.status_code < 300
            failed += not ok
            print(f"[{i}/{len(first) + len(patients)}] {r.status_code} {f.name[:50]}"
                  + ("" if ok else f"  ERROR: {r.text[:300]}"))
    print(f"\nDone in {time.time() - start:.0f} s. Failed: {failed}")


if __name__ == "__main__":
    main()
