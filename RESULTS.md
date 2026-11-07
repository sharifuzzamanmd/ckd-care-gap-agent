# Results log

## Step 2: NHANES 2021-2023 dataset (unweighted)
- Adults aged 20+ with eGFR and UACR: 5,343
- Probable CKD (eGFR < 60 or UACR >= 30, single visit): 925 (17.3%)
- Never told by a doctor (undiagnosed among CKD): 793 (85.7%)
- Notes: unweighted sample; single measurement, so "probable" CKD; eGFR uses race-free CKD-EPI 2021.
- Tests: tests/test_build_dataset.py (2 passed)

## Step 3: Model v1 (ckd_untested_v1), no kidney lab values as inputs
- Inputs: age, sex, SBP, DBP, diabetes, high BP diagnosis, HbA1c, BMI, hemoglobin, potassium, sodium
- Stacking ensemble (LR + NB + GB), SMOTE inside training folds only, isotonic calibration
- 5-fold CV AUC: 0.785 +/- 0.025 | Test AUC: 0.789 | Average precision: 0.506 | Brier: 0.114
- Flagging top 20% by risk catches 51.4% of CKD cases
- Simple rule (age 60+ OR diabetes OR high BP) flags 59%, catches 88.6%; model at same share catches 87.6%
- Conclusion: model matches the rule at broad screening; its value is ranking who to test first
- Fairness AUC: men 0.817, women 0.766; race/ethnicity groups 0.755 to 0.913 (small groups, wide uncertainty)
