"""Merge NHANES files, calculate eGFR (CKD-EPI 2021) and label CKD."""
from pathlib import Path
import numpy as np
import pandas as pd

RAW = Path("data/raw")


def load(name, cols):
    df = pd.read_sas(RAW / f"{name}.xpt", format="xport", encoding=None)
    return df[["SEQN"] + cols]


def egfr_ckd_epi_2021(scr, age, female):
    """Race-free CKD-EPI 2021 creatinine equation (mL/min/1.73m2)."""
    kappa = np.where(female, 0.7, 0.9)
    alpha = np.where(female, -0.241, -0.302)
    ratio = scr / kappa
    egfr = (142 * np.minimum(ratio, 1) ** alpha
            * np.maximum(ratio, 1) ** -1.200
            * 0.9938 ** age)
    return np.where(female, egfr * 1.012, egfr)


def build():
    df = load("DEMO_L", ["RIDAGEYR", "RIAGENDR", "RIDRETH3", "WTMEC2YR"])
    for name, cols in [
        ("ALB_CR_L", ["URDACT"]),
        ("BIOPRO_L", ["LBXSCR", "LBXSBU", "LBXSKSI", "LBXSNASI"]),
        ("GHB_L", ["LBXGH"]),
        ("BPXO_L", ["BPXOSY1", "BPXOSY2", "BPXOSY3", "BPXODI1", "BPXODI2", "BPXODI3"]),
        ("DIQ_L", ["DIQ010"]),
        ("BPQ_L", ["BPQ020"]),
        ("KIQ_U_L", ["KIQ022"]),
        ("BMX_L", ["BMXBMI"]),
        ("CBC_L", ["LBXHGB"]),
    ]:
        df = df.merge(load(name, cols), on="SEQN", how="left")

    df = df[(df.RIDAGEYR >= 20) & (df.WTMEC2YR > 0)].copy()  # adults with an exam

    df["female"] = (df.RIAGENDR == 2).astype(int)
    df["sbp"] = df[["BPXOSY1", "BPXOSY2", "BPXOSY3"]].mean(axis=1)
    df["dbp"] = df[["BPXODI1", "BPXODI2", "BPXODI3"]].mean(axis=1)
    df["diabetes"] = (df.DIQ010 == 1).astype(int)
    df["told_high_bp"] = (df.BPQ020 == 1).astype(int)
    df["told_kidney_disease"] = (df.KIQ022 == 1).astype(int)
    df["egfr"] = egfr_ckd_epi_2021(df.LBXSCR, df.RIDAGEYR, df.female == 1)
    df["uacr"] = df.URDACT

    # Label: probable CKD on a single visit (guidelines need 2 tests 3+ months apart)
    df = df.dropna(subset=["egfr", "uacr"])
    df["ckd"] = ((df.egfr < 60) | (df.uacr >= 30)).astype(int)
    # Undiagnosed = lab-defined CKD but never told by a doctor
    df["undiagnosed_ckd"] = ((df.ckd == 1) & (df.told_kidney_disease == 0)).astype(int)

    df = df.rename(columns={
        "RIDAGEYR": "age", "RIDRETH3": "race_eth", "WTMEC2YR": "weight",
        "LBXSBU": "bun", "LBXSKSI": "potassium", "LBXSNASI": "sodium",
        "LBXGH": "hba1c", "BMXBMI": "bmi", "LBXHGB": "hemoglobin",
    })
    keep = ["SEQN", "age", "female", "race_eth", "weight", "sbp", "dbp", "diabetes",
            "told_high_bp", "hba1c", "bmi", "hemoglobin", "bun", "potassium", "sodium",
            "egfr", "uacr", "told_kidney_disease", "ckd", "undiagnosed_ckd"]
    out = Path("data/processed")
    out.mkdir(parents=True, exist_ok=True)
    df[keep].to_csv(out / "nhanes_ckd.csv", index=False)
    print(f"{len(df)} adults | CKD {df.ckd.mean():.1%} | "
          f"undiagnosed among CKD {df.loc[df.ckd == 1, 'undiagnosed_ckd'].mean():.1%}")


if __name__ == "__main__":
    build()