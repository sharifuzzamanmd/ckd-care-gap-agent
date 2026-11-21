"""Turn raw values into labeled facts (high / low / normal) so the LLM does not have to guess."""

NAMES = {"age": "age", "sbp": "systolic blood pressure", "dbp": "diastolic blood pressure",
         "hba1c": "HbA1c", "bmi": "BMI", "hemoglobin": "hemoglobin",
         "potassium": "potassium", "sodium": "sodium"}
UNITS = {"sbp": "mmHg", "dbp": "mmHg", "hba1c": "%", "bmi": "kg/m2", "hemoglobin": "g/dL",
         "potassium": "mmol/L", "sodium": "mmol/L"}


def label(name: str, value: float, female: int) -> str:
    """Return 'high', 'low' or 'normal' using common adult reference ranges."""
    if name == "hba1c":
        return "high (diabetes range)" if value >= 6.5 else "borderline (prediabetes range)" if value >= 5.7 else "normal"
    if name == "sbp":
                return "high" if value >= 130 else "low" if value < 90 else "normal"
    if name == "dbp":
                return "high" if value >= 80 else "low" if value < 60 else "normal"
    if name == "bmi":
        return "high (obesity range)" if value >= 30 else "above normal (overweight range)" if value >= 25 else "normal"
    if name == "hemoglobin":
        return "low" if value < (12.0 if female else 13.0) else "normal"
    if name == "potassium":
        return "low" if value < 3.5 else "high" if value > 5.0 else "normal"
    if name == "sodium":
        return "low" if value < 135 else "high" if value > 145 else "normal"
    return ""


def describe(name: str, value, female: int) -> str:
    """One fact as text, e.g. 'hemoglobin: 11.9 g/dL (low)'."""
    if name in ("diabetes", "told_high_bp", "female"):
        nice = {"diabetes": "diabetes", "told_high_bp": "high blood pressure", "female": "female"}[name]
        return f"{nice}: {'yes' if value == 1 else 'no'}"
    if name == "age":
        return f"age: {value:g}"
    value = round(float(value), 1)  # 12.195 -> 12.2, easier to read
    text = f"{NAMES[name]}: {value:g} {UNITS[name]}"
    tag = label(name, value, female)
    return f"{text} ({tag})" if tag else text