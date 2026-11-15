"""Model API: CKD risk score + SHAP explanation for one patient."""
import os
import joblib
import pandas as pd
import shap
from fastapi import FastAPI
from pydantic import BaseModel

bundle = joblib.load(os.getenv("MODEL_PATH", "models/ckd_untested_v1.joblib"))
model, FEATURES = bundle["model"], bundle["features"]
explainer = shap.Explainer(
    lambda X: model.predict_proba(pd.DataFrame(X, columns=FEATURES))[:, 1],
    bundle["background"])

LABELS = {"age": "age", "female": "female", "sbp": "systolic BP", "dbp": "diastolic BP",
          "diabetes": "diabetes", "told_high_bp": "high blood pressure", "hba1c": "HbA1c",
          "bmi": "BMI", "hemoglobin": "hemoglobin", "potassium": "potassium", "sodium": "sodium"}
YES_NO = {"female", "diabetes", "told_high_bp"}

app = FastAPI(title="CKD risk model", version="1.1")


class Patient(BaseModel):
    age: float
    female: int
    sbp: float | None = None
    dbp: float | None = None
    diabetes: int = 0
    told_high_bp: int = 0
    hba1c: float | None = None
    bmi: float | None = None
    hemoglobin: float | None = None
    potassium: float | None = None
    sodium: float | None = None


@app.get("/health")
def health():
    return {"status": "ok", "features": FEATURES}


@app.post("/score")
def score(p: Patient):
    row = pd.DataFrame([p.model_dump()])[FEATURES].astype(float)
    risk = float(model.predict_proba(row)[:, 1][0])
    threshold = bundle["threshold"]

    # Risk level: high = top 20% (above threshold), low = under 10%, otherwise moderate
    level = "high" if risk >= threshold else "low" if risk < 0.10 else "moderate"

    # SHAP reasons, skipping values the patient doesn't have
    sv = explainer(row.fillna(bundle["background"].median()))
    contrib = sorted(zip(FEATURES, sv.values[0], row.iloc[0]), key=lambda t: -abs(t[1]))
    contrib = [c for c in contrib if not pd.isna(c[2])]
    drivers = [{"feature": f, "value": float(v),
                "effect": "raises risk" if s > 0 else "lowers risk", "shap": round(float(s), 4)}
               for f, s, v in contrib[:5]]

    # Plain-English explanation built from the SHAP reasons
    reasons = []
    for d in drivers:
        if d["feature"] in YES_NO:
            shown = "yes" if d["value"] == 1 else "no"
        else:
            shown = f"{d['value']:g}"
        reasons.append(f"{LABELS[d['feature']]} {shown} {d['effect']}")
    explanation = (f"{level.capitalize()} CKD risk ({round(risk * 100)}%). "
                   f"Main reasons: {'; '.join(reasons)}.")

    return {"risk": round(risk, 3), "risk_level": level, "explanation": explanation,
            "flag": risk >= threshold, "threshold": round(threshold, 3),
            "top_drivers": drivers, "model_version": "ckd_untested_v1"}