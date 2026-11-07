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

app = FastAPI(title="CKD risk model", version="1.0")


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
    sv = explainer(row.fillna(bundle["background"].median()))
    contrib = sorted(zip(FEATURES, sv.values[0], row.iloc[0]), key=lambda t: -abs(t[1]))
    contrib = [c for c in contrib if not pd.isna(c[2])]  # only explain values we actually have
    drivers = [{"feature": f, "value": float(v),
                "effect": "raises risk" if s > 0 else "lowers risk", "shap": round(float(s), 4)}
               for f, s, v in contrib[:5]]
    return {"risk": round(risk, 3), "flag": risk >= bundle["threshold"],
            "threshold": round(bundle["threshold"], 3), "top_drivers": drivers,
            "model_version": "ckd_untested_v1"}