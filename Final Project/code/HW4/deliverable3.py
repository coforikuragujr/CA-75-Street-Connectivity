import os
import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt

# Config: Input paths and outputs
ACS_CSV = r"C:\Users\Charles\OneDrive\Desktop\Misc\IIT\CS 579\Assignment 3\ca75_acs_blockgroups_updated.csv"
BG_SHP  = r"C:\Users\Charles\Downloads\tl_2023_17_bg\tl_2023_17_bg.shp"
COMMUNITY_SHP = r""

OUT_GPKG = "ca75_acs_bg_maps.gpkg"
OUT_DIR  = "maps_ca75"
os.makedirs(OUT_DIR, exist_ok=True)

# Fixed FIPS for Illinois / Cook County
STATEFP = "17"   # Illinois
COUNTYFP = "031" # Cook County

# Helpers
def make_geoid_bg_from_parts(df):
    """Build 12-digit block-group GEOID from TIGER fields if composite GEOID is absent."""
    for fld in ["STATEFP","COUNTYFP","TRACTCE","BLKGRPCE"]:
        if fld not in df.columns:
            raise SystemExit(f"Block-group layer missing required field: {fld}")
    return (
        df["STATEFP"].astype(str).str.zfill(2)
        + df["COUNTYFP"].astype(str).str.zfill(3)
        + df["TRACTCE"].astype(str).str.zfill(6)
        + df["BLKGRPCE"].astype(str).str.zfill(1)
    )

def ensure_geoid_bg_strings(bg_gdf, acs_df):
    """Ensure both geometry and ACS frames carry a string 12-digit GEOID_BG key for merging."""
    # BG side: use existing GEOID or build from parts
    if "GEOID" in bg_gdf.columns:
        bg_gdf["GEOID_BG"] = bg_gdf["GEOID"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(12)
    else:
        bg_gdf["GEOID_BG"] = make_geoid_bg_from_parts(bg_gdf)
    # ACS side: accept GEOID_BG, GEOID, or build from TRACT+BG
    if "GEOID_BG" in acs_df.columns:
        acs_df["GEOID_BG"] = acs_df["GEOID_BG"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(12)
    elif "GEOID" in acs_df.columns:
        acs_df["GEOID_BG"] = acs_df["GEOID"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(12)
    elif {"TRACT","BG"}.issubset(acs_df.columns):
        acs_df["GEOID_BG"] = STATEFP + COUNTYFP + acs_df["TRACT"].astype(str).str.zfill(6) + acs_df["BG"].astype(str).str.zfill(1)
    else:
        raise SystemExit("ACS CSV needs GEOID_BG or (GEOID) or (TRACT + BG).")
    # Force string dtype for merge compatibility
    bg_gdf["GEOID_BG"] = bg_gdf["GEOID_BG"].astype(str)
    acs_df["GEOID_BG"] = acs_df["GEOID_BG"].astype(str)
    return bg_gdf, acs_df

def have_mapclassify():
    """Return True if mapclassify is installed (enables built-in quantile classification)."""
    try:
        import mapclassify  # noqa: F401
        return True
    except Exception:
        return False

def plot_choropleth(gdf, field, title, fname, use_quantiles=True):
    """Generic choropleth helper with NA filtering and quantile fallback."""
    if field not in gdf.columns:
        print(f"[warn] Field {field} not found; skipping map.")
        return
    data = pd.to_numeric(gdf[field], errors="coerce")
    mask = data.notna() & np.isfinite(data)
    if mask.sum() == 0:
        print(f"[warn] No usable values for {field}; skipping map.")
        return
    gsub = gdf.loc[mask].copy()
    out_path = os.path.join(OUT_DIR, fname)
    try:
        if use_quantiles and have_mapclassify():
            # mapclassify will reduce k if there are too few unique values
            ax = gsub.plot(column=field, scheme="Quantiles", k=5, legend=True,
                           figsize=(7,7), edgecolor="black", linewidth=0.25)
        else:
            # Safe fallback using qcut (handles duplicate bins)
            k = min(5, max(1, gsub[field].nunique()))
            cats = pd.qcut(gsub[field], q=k, duplicates="drop")
            gsub["_qcat"] = cats.astype(str)
            ax = gsub.plot(column="_qcat", legend=True,
                           figsize=(7,7), edgecolor="black", linewidth=0.25)
        ax.set_axis_off()
        ax.set_title(title)
        plt.tight_layout()
        plt.savefig(out_path, dpi=200)
        plt.close()
        print(f"Wrote map: {out_path}")
    except Exception as e:
        print(f"[warn] Failed to render {field}: {e}")

def safe_rate(num, den):
    """Compute 100 * num/den with guardrails for zero/NA denominators."""
    out = (num / den) * 100
    return out.mask((den==0) | den.isna() | num.isna()).round(2)

# 1) Read ACS CSV
if not os.path.exists(ACS_CSV):
    raise SystemExit(f"ACS CSV not found: {ACS_CSV}")

# Keep identifiers as strings if present
read_kwargs = {"dtype": {"GEOID_BG":"string","GEOID":"string","TRACT":"string","BG":"string"}}
try:
    acs = pd.read_csv(ACS_CSV, **read_kwargs)
except Exception:
    acs = pd.read_csv(ACS_CSV)

# 2) Read Block Group geometry
if not os.path.exists(BG_SHP) and not BG_SHP.startswith("zip://"):
    raise SystemExit(f"Block group shapefile not found: {BG_SHP}")

bg = gpd.read_file(BG_SHP)

# If statewide, filter to Cook County only
if "COUNTYFP" in bg.columns:
    bg = bg.loc[bg["COUNTYFP"] == COUNTYFP].copy()
elif "GEOID" in bg.columns:
    bg = bg.loc[bg["GEOID"].astype(str).str.startswith(STATEFP + COUNTYFP)].copy()

# 3) Ensure matching keys
bg, acs = ensure_geoid_bg_strings(bg, acs)

# 4) Optional: clip to Community Area 75
if COMMUNITY_SHP:
    if not os.path.exists(COMMUNITY_SHP):
        print(f"[warn] COMMUNITY_SHP not found: {COMMUNITY_SHP} — skipping clip.")
    else:
        comm = gpd.read_file(COMMUNITY_SHP)
        # Try common field names for CA number or name
        ca_field_num = next((c for c in ["AREA_NUMBE","area_numbe","CA","ca","COMMUNITY_A","community_a","commarea"] if c in comm.columns), None)
        ca_field_name = next((c for c in ["COMMUNITY","community","Community","area_num_1","COMMUNITY_"] if c in comm.columns), None)
        if ca_field_num:
            comm75 = comm.loc[comm[ca_field_num].astype(str).str.strip().isin(["75","075"])].copy()
        elif ca_field_name:
            comm75 = comm.loc[comm[ca_field_name].astype(str).str.upper().str.strip() == "MORGAN PARK"].copy()
        else:
            raise SystemExit("Could not find a recognizable CA number/name field to clip.")
        if comm75.empty:
            raise SystemExit("Did not find CA 75 (Morgan Park) in the Community Areas file.")
        # Align CRS and perform overlay clip
        comm75 = comm75.to_crs(bg.crs)
        try:
            bg = gpd.overlay(bg, comm75[["geometry"]], how="intersection")
        except Exception as e:
            print("[warn] Overlay failed (continuing without clip):", e)

# 5) Join ACS to geometry
g = bg.merge(acs, on="GEOID_BG", how="inner")

# 6) Ensure numeric types & (re)compute missing/empty rates
# Coerce raw counts if present
for c in ["pop","white","black","asian","owner","renter","hisp_tot","hisp",
          "units","vac_units","units_denom","u_20_49","u_50p"]:
    if c in g.columns:
        g[c] = pd.to_numeric(g[c], errors="coerce")

# Recompute standard percentages if missing or entirely empty
def needs_compute(df, field, deps):
    """Return True if field is missing or has zero non-NA values and dependencies exist."""
    return (field not in df.columns) or (pd.to_numeric(df.get(field), errors="coerce").notna().sum() == 0 and all(d in df.columns for d in deps))

if needs_compute(g, "white_pct", ["white","pop"]):
    g["white_pct"] = safe_rate(g["white"], g["pop"])
if needs_compute(g, "black_pct", ["black","pop"]):
    g["black_pct"] = safe_rate(g["black"], g["pop"])
if needs_compute(g, "asian_pct", ["asian","pop"]):
    g["asian_pct"] = safe_rate(g["asian"], g["pop"])
if needs_compute(g, "owner_pct", ["owner","renter"]):
    denom = g["owner"] + g["renter"]
    g["owner_pct"] = safe_rate(g["owner"], denom)

if needs_compute(g, "hisp_pct", ["hisp","hisp_tot"]):
    g["hisp_pct"] = safe_rate(g.get("hisp", pd.Series(dtype="float64")), g.get("hisp_tot", pd.Series(dtype="float64")))
if needs_compute(g, "vac_rate", ["vac_units","units"]):
    g["vac_rate"] = safe_rate(g.get("vac_units", pd.Series(dtype="float64")), g.get("units", pd.Series(dtype="float64")))
if needs_compute(g, "u_20plus_pct", ["u_20_49","u_50p","units_denom"]):
    numer = g.get("u_20_49", pd.Series(dtype="float64")) + g.get("u_50p", pd.Series(dtype="float64"))
    g["u_20plus_pct"] = safe_rate(numer, g.get("units_denom", pd.Series(dtype="float64")))

# Quick diagnostics for mapped fields
print("=== Field availability (non-null counts after join/compute) ===")
for fld in ["hisp_pct","vac_rate","u_20plus_pct","black_pct","owner_pct","pop"]:
    if fld in g.columns:
        print(f"{fld}: {int(pd.to_numeric(g[fld], errors='coerce').notna().sum())} non-null")

# 7) Write spatial output (GPKG w/ fallback)
# Drop ID columns that often confuse GPKG schema
for idcol in ["TRACT","BG"]:
    if idcol in g.columns:
        g = g.drop(columns=[idcol])

# Ensure CRS exists (copy from BG if needed)
if g.crs is None:
    g = g.set_crs(bg.crs)

try:
    g.to_file(OUT_GPKG, layer="ca75_bg_acs", driver="GPKG")
    print(f"Wrote {OUT_GPKG}")
except Exception as e:
    print("[warn] Failed to write GPKG:", e)
    OUT_GEOJSON = "ca75_acs_bg_maps.geojson"
    g.to_file(OUT_GEOJSON, driver="GeoJSON")
    print(f"Fell back to {OUT_GEOJSON}")

# 8) Make maps (six variables)
plots = [
    ("black_pct", "Black population (%)", "map_black_pct.png"),
    ("hisp_pct", "Hispanic/Latino (%)", "map_hisp_pct.png"),
    ("owner_pct", "Owner-occupied share (%)", "map_owner_pct.png"),
    ("vac_rate", "Housing vacancy rate (%)", "map_vacancy_rate.png"),
    ("u_20plus_pct", "Large multifamily (20+ units) share (%)", "map_large_mf_pct.png"),
    ("pop", "Total population (count)", "map_pop_count.png"),
]

for field, title, fname in plots:
    plot_choropleth(g, field, title, fname, use_quantiles=True)

print("Done. Check the maps in:", os.path.abspath(OUT_DIR))
