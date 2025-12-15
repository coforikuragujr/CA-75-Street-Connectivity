# aggregatetobg.py
# Merge network metrics (bg_metrics.csv) with ACS block-group data for CA 75.
# Robust: keeps all ACS columns, normalizes headers, and (re)computes key rates if missing.

import os
import pandas as pd
import numpy as np

ACS_CSV   = r"data/census/ca75_acs_blockgroups_updated.csv"
METRICS   = r"outputs/tables/bg_metrics.csv"
OUT_DIR   = r"outputs/tables"
OUT_CSV   = os.path.join(OUT_DIR, "bg_joined.csv")

os.makedirs(OUT_DIR, exist_ok=True)

def normalize_headers(df):
    # strip/normalize column names
    df.columns = [c.strip() for c in df.columns]
    return df

# Read ACS and metrics
acs = pd.read_csv(ACS_CSV, dtype=str, low_memory=False)
acs = normalize_headers(acs)
metrics = pd.read_csv(METRICS)
metrics.columns = [c.strip() for c in metrics.columns]

# Normalize join key
acs["GEOID_BG"] = acs["GEOID_BG"].astype(str).str[-12:].str.zfill(12)
metrics["GEOID_BG"] = metrics["GEOID_BG"].astype(str).str[-12:].str.zfill(12)

# Coerce numeric where useful (safe)
num_like = [
    "pop","white","black","asian",
    "owner","renter",
    "hisp_tot","hisp",
    "units","vac_units","units_denom",
    "u_20_49","u_50p",
    "owner_pct","vac_rate","black_pct","hisp_pct","u_20plus_pct"
]
for c in num_like:
    if c in acs.columns:
        acs[c] = pd.to_numeric(acs[c], errors="coerce")

# (Re)compute key rates if missing/empty
def pct(n, d):
    n = pd.to_numeric(n, errors="coerce")
    d = pd.to_numeric(d, errors="coerce")
    out = (n / d) * 100.0
    return out.mask((d <= 0) | d.isna() | n.isna()).round(2)

if ("owner_pct" not in acs.columns) or (pd.to_numeric(acs.get("owner_pct"), errors="coerce").notna().sum() == 0):
    if {"owner","renter"}.issubset(acs.columns):
        denom = acs["owner"] + acs["renter"]
        acs["owner_pct"] = pct(acs["owner"], denom)

if ("vac_rate" not in acs.columns) or (pd.to_numeric(acs.get("vac_rate"), errors="coerce").notna().sum() == 0):
    if {"vac_units","units"}.issubset(acs.columns):
        acs["vac_rate"] = pct(acs["vac_units"], acs["units"])

if ("black_pct" not in acs.columns) or (pd.to_numeric(acs.get("black_pct"), errors="coerce").notna().sum() == 0):
    if {"black","pop"}.issubset(acs.columns):
        acs["black_pct"] = pct(acs["black"], acs["pop"])

# For completeness, recompute Hispanic% and 20+ units% if missing
if ("hisp_pct" not in acs.columns) or (pd.to_numeric(acs.get("hisp_pct"), errors="coerce").notna().sum() == 0):
    if {"hisp","hisp_tot"}.issubset(acs.columns):
        acs["hisp_pct"] = pct(acs["hisp"], acs["hisp_tot"])

if ("u_20plus_pct" not in acs.columns) or (pd.to_numeric(acs.get("u_20plus_pct"), errors="coerce").notna().sum() == 0):
    if {"u_20_49","u_50p","units_denom"}.issubset(acs.columns):
        numer = pd.to_numeric(acs["u_20_49"], errors="coerce") + pd.to_numeric(acs["u_50p"], errors="coerce")
        acs["u_20plus_pct"] = pct(numer, acs["units_denom"])

# Merge: keep ALL ACS columns, then add metrics
joined = acs.merge(metrics, on="GEOID_BG", how="left")

# Final numeric coercion for analysis convenience
for c in joined.columns:
    if c not in ["GEOID_BG","TRACT","BG"] and joined[c].dtype == object:
        # try to coerce numerics but don't force
        try:
            joined[c] = pd.to_numeric(joined[c], errors="ignore")
        except Exception:
            pass

# Write and small report
joined.to_csv(OUT_CSV, index=False)
print(f"[OK] Wrote merged table: {OUT_CSV}")

have = {k: (k in joined.columns and pd.to_numeric(joined[k], errors='coerce').notna().sum()) for k in ["owner_pct","vac_rate","black_pct"]}
print("[INFO] Non-null counts:", have)
print("Rows:", len(joined))
