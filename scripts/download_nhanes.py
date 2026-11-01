"""Download NHANES August 2021-August 2023 files needed for the CKD model."""
from pathlib import Path
import urllib.request

BASE = "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2021/DataFiles/"
FILES = ["DEMO_L", "ALB_CR_L", "BIOPRO_L", "GHB_L", "BPXO_L",
         "DIQ_L", "BPQ_L", "KIQ_U_L", "BMX_L", "CBC_L"]

out = Path("data/raw")
out.mkdir(parents=True, exist_ok=True)

for name in FILES:
    target = out / f"{name}.xpt"
    if target.exists():
        print(f"skip {name} (already downloaded)")
        continue
    req = urllib.request.Request(BASE + f"{name}.xpt", headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as r, open(target, "wb") as f:
        f.write(r.read())
    print(f"saved {target}")