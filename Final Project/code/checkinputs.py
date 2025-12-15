# checkinputs.py
# Basic input validation for the final project (no virtual env required).
# - Verifies required ACS columns
# - Ensures/derives GEOID_BG, TRACT, BG (derives if missing)
# - Light range checks on percentage fields
# - Confirms overlap between CSV GEOIDs and geometry (GPKG/GeoJSON)

import sys, os
import pandas as pd

# ---- Paths to your HW4 inputs (unchanged names) ----
ACS_CSV = r"data/census/ca75_acs_blockgroups_updated.csv"
SPATIAL = r"data/spatial/ca75_acs_bg_maps.gpkg"   # fallback to .geojson if needed
LAYER   = "ca75_bg_acs"                           # keep as-is; will try fallback

def fail(msg, code=1):
    print(f"[FAIL] {msg}")
    sys.exit(code)

def ok(msg):
    print(f"[OK] {msg}")

# ---- 1) CSV existence ----
if not os.path.exists(ACS_CSV):
    fail(f"ACS CSV not found: {ACS_CSV}")

# ---- 2) Read CSV and verify required columns ----
need_cols_core = {
    "GEOID_BG",
    "pop","white","black","asian",
    "owner","renter",
    "hisp_tot","hisp",
    "units","vac_units",
    "units_denom","u_20_49","u_50p",
    "black_pct","owner_pct","asian_pct",
    "hisp_pct","vac_rate","u_20plus_pct"
}
optional_id_cols = {"TRACT","BG"}

df = pd.read_csv(ACS_CSV, dtype=str, low_memory=False)

missing_core = [c for c in need_cols_core if c not in df.columns]
if missing_core:
    fail(f"Missing required columns in CSV: {missing_core}")

# ---- 3) Normalize GEOID_BG and derive TRACT/BG if missing ----
df["GEOID_BG"] = df["GEOID_BG"].astype(str).str[-12:].str.zfill(12)

if "TRACT" not in df.columns:
    df["TRACT"] = df["GEOID_BG"].str[5:11]
    print("[INFO] Derived TRACT from GEOID_BG.")

if "BG" not in df.columns:
    df["BG"] = df["GEOID_BG"].str[-1:]
    print("[INFO] Derived BG from GEOID_BG.")

dups = df["GEOID_BG"].duplicated().sum()
if dups > 0:
    fail(f"GEOID_BG duplicates found: {dups}")

if (df["GEOID_BG"].str.len()!=12).any():
    fail("Some GEOID_BG values are not 12 characters after normalization.")

ok(f"CSV rows: {len(df)}; unique GEOIDs: {df['GEOID_BG'].nunique()}")

# ---- 4) Numeric coercion and range checks for rates ----
rate_fields = ["black_pct","owner_pct","asian_pct","hisp_pct","vac_rate","u_20plus_pct"]
for c in rate_fields:
    df[c] = pd.to_numeric(df[c], errors="coerce")

for c in rate_fields:
    nn = int(df[c].notna().sum())
    print(f"[INFO] {c}: non-null {nn}/{len(df)}")

for c in rate_fields:
    bad = df.loc[(df[c].notna()) & ((df[c] < -0.01) | (df[c] > 100.01)), c]
    if not bad.empty:
        fail(f"Out-of-range values in {c}: {list(bad.head(5))} ...")

ok("Rate fields look within 0..100 or NA.")

# ---- 5) Geometry file and GEOID overlap ----
geom_found = False
try:
    import geopandas as gpd
except Exception:
    print("[WARN] geopandas not available; skipping geometry overlap check.")
    print("[READY] Inputs pass basic CSV checks.")
    sys.exit(0)

if os.path.exists(SPATIAL):
    try:
        g = gpd.read_file(SPATIAL, layer=LAYER)
        geom_found = True
    except Exception:
        try:
            g = gpd.read_file(SPATIAL)  # single-layer
            geom_found = True
        except Exception as e:
            print(f"[WARN] Could not read {SPATIAL}: {e}")
else:
    gj = "data/spatial/ca75_acs_bg_maps.geojson"
    if os.path.exists(gj):
        try:
            g = gpd.read_file(gj)
            SPATIAL = gj
            geom_found = True
        except Exception as e:
            print(f"[WARN] Could not read {gj}: {e}")

if not geom_found:
    print("[WARN] No spatial file could be read; skipping geometry overlap check.")
    print("[READY] Inputs pass basic CSV checks.")
    sys.exit(0)

if "GEOID_BG" not in g.columns:
    if "GEOID" in g.columns:
        g["GEOID_BG"] = g["GEOID"].astype(str).str[-12:].str.zfill(12)
    else:
        fail("Geometry lacks GEOID/GEOID_BG for overlap check.")

common = set(df["GEOID_BG"]).intersection(set(g["GEOID_BG"]))
if len(common) == 0:
    fail(f"No overlap between CSV GEOIDs and geometry in {SPATIAL}.")

ok(f"Geometry features: {len(g)}; GEOIDs in common: {len(common)}")
print("[READY] Inputs pass checks and are ready for Step 3.")
