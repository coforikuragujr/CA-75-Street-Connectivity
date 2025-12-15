# robustcheck.py
# 100-m buffer robustness check: compare correlations using base BG densities
# vs densities recomputed with a 100 m buffered BG footprint.

import os
import numpy as np
import pandas as pd
import geopandas as gpd

GPKG   = r"data/spatial/ca75_acs_bg_maps.gpkg"
LAYER  = "ca75_bg_acs"
JOINED = r"outputs/tables/bg_joined.csv"

def collapse_suffixes(df, base):
    """If base_x/base_y exist, create base using _y then _x, then drop the suffixed cols."""
    x, y = f"{base}_x", f"{base}_y"
    if x in df.columns and y in df.columns:
        df[base] = df[y].where(pd.to_numeric(df[y], errors="coerce").notna(),
                               pd.to_numeric(df[x], errors="coerce"))
        df.drop(columns=[x, y], inplace=True, errors="ignore")
    elif y in df.columns and base not in df.columns:
        df[base] = df[y]
        df.drop(columns=[y], inplace=True, errors="ignore")
    elif x in df.columns and base not in df.columns:
        df[base] = df[x]
        df.drop(columns=[x], inplace=True, errors="ignore")

# Read geometry (layer fallback)
try:
    g = gpd.read_file(GPKG, layer=LAYER)
except Exception:
    g = gpd.read_file(GPKG)

# Ensure key on geometry
if "GEOID_BG" not in g.columns and "GEOID" in g.columns:
    g["GEOID_BG"] = g["GEOID"].astype(str).str[-12:].str.zfill(12)

# Read joined attributes
df = pd.read_csv(JOINED)
df.columns = [c.strip() for c in df.columns]
df["GEOID_BG"] = df["GEOID_BG"].astype(str).str[-12:].str.zfill(12)

# Drop overlapping non-geometry columns to avoid _x/_y
geom_keep = {"geometry", "GEOID_BG", "GEOID", "TRACT", "BG"}
overlap = (set(g.columns) & set(df.columns)) - {"GEOID_BG"}
drop_these = [c for c in overlap if c not in geom_keep]
if drop_these:
    g = g.drop(columns=drop_these, errors="ignore")

# Merge geometry + attributes
joined = g.merge(df, on="GEOID_BG", how="inner")

# Collapse suffixes for all fields we care about
for base in [
    "owner_pct","vac_rate","black_pct",
    "nodes_in_bg","edges_km","node_density","edge_km_density",
    "betweenness_mean","aspl_mean","area_km2"
]:
    collapse_suffixes(joined, base)

# Sanity report
want = ["owner_pct","vac_rate","black_pct","node_density","edge_km_density"]
print("=== Field availability (post-merge) ===")
for c in want:
    ok = c in joined.columns
    nn = pd.to_numeric(joined[c], errors="coerce").notna().sum() if ok else 0
    print(f"{c}: in_columns={ok} non_null={nn}")

# Project to metric CRS and build a 100 m buffer around BGs
jm = joined.to_crs(3857)
jm["area_km2_buf100"] = jm.geometry.buffer(100).area / 1_000_000.0  # meters->km²

# Recompute densities using buffered area (same numerators)
if "nodes_in_bg" in jm.columns:
    jm["node_density_buf100"] = pd.to_numeric(jm["nodes_in_bg"], errors="coerce") / jm["area_km2_buf100"]
if "edges_km" in jm.columns:
    jm["edge_km_density_buf100"] = pd.to_numeric(jm["edges_km"], errors="coerce") / jm["area_km2_buf100"]

def corr_pair(df, x, y):
    a = pd.to_numeric(df.get(x), errors="coerce")
    b = pd.to_numeric(df.get(y), errors="coerce")
    d = pd.DataFrame({x:a, y:b}).dropna()
    if d.empty:
        return (np.nan, np.nan, 0)
    return (d[x].corr(d[y], method="pearson"),
            d[x].corr(d[y], method="spearman"),
            len(d))

# Compare base vs buffered for two relationships from your proposal
comparisons = [
    (("node_density","node_density_buf100"), "owner_pct"),
    (("edge_km_density","edge_km_density_buf100"), "owner_pct"),
    (("node_density","node_density_buf100"), "vac_rate"),
]

for (x_base, x_buf), y in comparisons:
    p0,s0,n0 = corr_pair(jm, x_base, y)
    p1,s1,n1 = corr_pair(jm, x_buf, y)
    print(f"\n{y} ~ {x_base} vs {x_buf} | n={n0}/{n1}")
    print(f"  base: Pearson {p0:.3f}  Spearman {s0:.3f}")
    print(f"  buf : Pearson {p1:.3f}  Spearman {s1:.3f}")

print("\nRobustness check finished!")
