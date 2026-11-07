"""Train a leakage-free stacking model that predicts CKD WITHOUT kidney lab values.

Use case: patients who were never tested (no eGFR/UACR). Kidney labs, BUN and
creatinine are excluded from the inputs because they define the label.
"""
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from imblearn.over_sampling import SMOTE
from imblearn.pipeline import Pipeline
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import GradientBoostingClassifier, StackingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, recall_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.naive_bayes import GaussianNB
from sklearn.preprocessing import StandardScaler

FEATURES = ["age", "female", "sbp", "dbp", "diabetes", "told_high_bp",
            "hba1c", "bmi", "hemoglobin", "potassium", "sodium"]
TARGET = "ckd"


def make_model():
    stack = StackingClassifier(
        estimators=[
            ("lr", LogisticRegression(max_iter=1000)),
            ("nb", GaussianNB()),
            ("gb", GradientBoostingClassifier(random_state=42)),
        ],
        final_estimator=LogisticRegression(max_iter=1000),
        cv=5,
    )
    # SMOTE sits INSIDE the pipeline, so it only ever sees training folds.
    return Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("smote", SMOTE(random_state=42)),
        ("stack", stack),
    ])


def main(path="data/processed/nhanes_ckd.csv"):
    df = pd.read_csv(path)
    X, y = df[FEATURES], df[TARGET]
    X_train, X_test, y_train, y_test, df_train, df_test = train_test_split(
        X, y, df, test_size=0.2, stratify=y, random_state=42)

    cv = StratifiedKFold(5, shuffle=True, random_state=42)
    cv_auc = cross_val_score(make_model(), X_train, y_train, cv=cv, scoring="roc_auc")
    print(f"5-fold CV AUC on training data: {cv_auc.mean():.3f} +/- {cv_auc.std():.3f}")

    # Calibrate so a 30% score means about 30 in 100 patients have CKD.
    model = CalibratedClassifierCV(make_model(), method="isotonic", cv=5)
    model.fit(X_train, y_train)

    p = model.predict_proba(X_test)[:, 1]
    threshold = np.quantile(p, 0.80)  # flag the top 20% riskiest patients
    print(f"Test AUC: {roc_auc_score(y_test, p):.3f}")
    print(f"Test average precision: {average_precision_score(y_test, p):.3f}")
    print(f"Brier score (calibration, lower is better): {brier_score_loss(y_test, p):.3f}")
    print(f"Sensitivity when flagging top 20%: {recall_score(y_test, p >= threshold):.3f}")

    # Baseline: a simple rule a clinic could use without any model
    rule = ((X_test.age >= 60) | (X_test.diabetes == 1) | (X_test.told_high_bp == 1)).astype(int)
    print(f"\nSimple rule (age 60+ OR diabetes OR high BP): flags {rule.mean():.0%} of patients, "
          f"sensitivity {recall_score(y_test, rule):.3f}")
    same_share = p >= np.quantile(p, 1 - rule.mean())
    print(f"Model flagging the same share: sensitivity {recall_score(y_test, same_share):.3f}")

    print("\nFairness check (AUC by group):")
    for col in ["female", "race_eth"]:
        for g, idx in df_test.groupby(col).groups.items():
            yt = y_test.loc[idx]
            if yt.nunique() == 2 and len(yt) >= 30:
                print(f"  {col}={g}: AUC {roc_auc_score(yt, p[y_test.index.get_indexer(idx)]):.3f} (n={len(yt)})")

    Path("models").mkdir(exist_ok=True)
    joblib.dump({"model": model, "features": FEATURES, "threshold": float(threshold),
                 "background": X_train.sample(min(100, len(X_train)), random_state=42)},
                "models/ckd_untested_v1.joblib")
    print("\nSaved models/ckd_untested_v1.joblib")


if __name__ == "__main__":
    main()