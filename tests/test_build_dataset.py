"""Automatic checks for the dataset code."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_dataset import egfr_ckd_epi_2021


def test_egfr_known_values():
    # Creatinine 1.0 mg/dL, age 50: about 92 for a man, about 69 for a woman
    result = egfr_ckd_epi_2021(np.array([1.0, 1.0]), np.array([50, 50]), np.array([False, True]))
    assert round(result[0]) == 92
    assert round(result[1]) == 69


def test_dataset_is_sensible():
    df = pd.read_csv("data/processed/nhanes_ckd.csv")
    assert len(df) > 4000                      # thousands of adults
    assert df["age"].min() >= 20               # adults only
    assert set(df["ckd"].unique()) <= {0, 1}   # label is 0 or 1
    # every CKD label matches the definition
    expected = ((df.egfr < 60) | (df.uacr >= 30)).astype(int)
    assert (df["ckd"] == expected).all()
    # undiagnosed only when CKD and never told
    assert (df.loc[df.undiagnosed_ckd == 1, "ckd"] == 1).all()