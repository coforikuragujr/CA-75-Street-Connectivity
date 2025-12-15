# analysismaps.py
# Make choropleths for network + ACS outcomes and quick bivariate plots.
# Saves outputs into subfolders:
#   outputs/figures/network_metrics/
#   outputs/figures/acs_outcomes/
#   outputs/figures/bivariate_scatter/

import os
import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt

# Inputs/outputs
GPKG   = r"data/spatial/ca75_acs_bg_maps.gpkg"
LAYER  = "ca75_bg_acs"
JOINED = r"outputs/tables/bg_joined.csv"

OUTDIR_BASE = r"outputs/figures"
DIR_NETWORK = os.path.join(OUTDIR_BASE, "networkmetrics")
DIR_OUTCOME = os.path.join(OUTDIR_BASE, "acsoutcomes")
DIR_SCATTER = os.path.join(OUTDIR_BASE, "bivariatescatter")
for d in (OUTDIR_BASE, DIR_NETWORK, DIR_OUTCOME, DIR_SCATTER):
    os.makedirs(d, exist_ok=True)

# Read geometry (fallback: read without layer)
try:
    g = gpd.read_file(GPKG, layer=LAYER)
except Exception:
    g = gpd.read_file(GPKG)

# Read joined attributes
df = pd.read_csv(JOINED)
df.columns = [c.strip() for c in df.columns]
df["GEOID_BG"] = df["GEOID_BG"].astype(str).str[-12:].str.zfill(12)

# Ensure geometry has join key
if "GEOID_BG" not in g.columns and "GEOID" in g.columns:
    g["GEOID_BG"] = g["GEOID"].astype(str).str[-12:].str.zfill(12)

# Drop overlapping non-geometry columns to avoid _x/_y suffixes
geom_cols = {"geometry", "GEOID_BG", "GEOID", "TRACT", "BG"}
overlap = (set(g.columns) & set(df.columns)) - {"GEOID_BG"}
drop_these = [c for c in overlap if c not in geom_cols]
if drop_these:
    g = g.drop(columns=drop_these, errors="ignore")

# Merge
g = g.merge(df, on="GEOID_BG", how="inner")

# Collapse any _x/_y pairs if they slipped in
def collapse_suffixes(geodf, base):
    x, y = f"{base}_x", f"{base}_y"
    if x in geodf.columns and y in geodf.columns:
        geodf[base] = geodf[y].where(geodf[y].notna(), geodf[x])
    elif y in geodf.columns and base not in geodf.columns:
        geodf[base] = geodf[y]
    for c in (x, y):
        if c in geodf.columns:
            geodf.drop(columns=c, inplace=True)

for base in ["owner_pct","vac_rate","black_pct",
             "node_density","edge_km_density","betweenness_mean","aspl_mean"]:
    collapse_suffixes(g, base)

# Quick field availability check
want_fields = [
    "node_density","edge_km_density","betweenness_mean","aspl_mean",
    "owner_pct","vac_rate","black_pct"
]
print("=== Field availability after join ===")
for f in want_fields:
    nn = pd.to_numeric(g.get(f), errors="coerce").notna().sum() if f in g.columns else 0
    print(f"{f}: in_columns={f in g.columns} non_null={nn}")

# Helper: quantile choropleth
def qmap(geodf, field, title, out_dir, fname, k=5):
    if field not in geodf.columns:
        print(f"[warn] Field {field} not found; skipped map.")
        return
    data = pd.to_numeric(geodf[field], errors="coerce")
    mask = data.notna() & np.isfinite(data)
    if mask.sum() == 0:
        print(f"[warn] No values for {field}; skipped map.")
        return
    sub = geodf.loc[mask].copy()
    try:
        ax = sub.plot(column=field, scheme="Quantiles", k=k, legend=True,
                      figsize=(7,7), edgecolor="black", linewidth=0.25)
    except Exception:
        ax = sub.plot(column=field, legend=True, figsize=(7,7),
                      edgecolor="black", linewidth=0.25)
    ax.set_axis_off()
    ax.set_title(title)
    plt.tight_layout()
    out = os.path.join(out_dir, fname)
    plt.savefig(out, dpi=200)
    plt.close()
    print("Wrote", out)

# Helper: scatter with trend line and r values
def scatter(x, y, title, out_dir, fname, xlabel=None, ylabel=None):
    if x not in g.columns or y not in g.columns:
        print(f"[warn] Missing fields for scatter {x} vs {y}")
        return
    d = g[[x,y]].apply(pd.to_numeric, errors="coerce").dropna()
    if d.empty:
        print(f"[warn] No data for scatter {x} vs {y}")
        return
    X = d[x].values
    Y = d[y].values
    if len(np.unique(X)) > 1:
        m, b = np.polyfit(X, Y, 1)
        xs = np.sort(X)
        yhat = m*xs + b
        r = np.corrcoef(X, Y)[0,1]
    else:
        xs = None
        yhat = None
        r = np.nan

    plt.figure(figsize=(6,5))
    plt.scatter(X, Y, s=25, alpha=0.85)
    if yhat is not None:
        plt.plot(xs, yhat, linewidth=2)
    plt.title(title + (f"\nPearson r={r:.2f}" if np.isfinite(r) else ""))
    plt.xlabel(xlabel or x)
    plt.ylabel(ylabel or y)
    plt.tight_layout()
    out = os.path.join(out_dir, fname)
    plt.savefig(out, dpi=200)
    plt.close()
    print("Wrote", out)

    # console correlations
    pear = d[x].corr(d[y], method="pearson")
    spear = d[x].corr(d[y], method="spearman")
    print(f"[corr] {x} ~ {y} | Pearson={pear:.3f}, Spearman={spear:.3f}")

# 1) MAPS — network metrics
qmap(g, "node_density",     "Node density (nodes / km²)",           DIR_NETWORK, "map_node_density.png")
qmap(g, "edge_km_density",  "Edge density (km road / km²)",         DIR_NETWORK, "map_edge_density.png")
qmap(g, "betweenness_mean", "Betweenness centrality (mean, nodes)", DIR_NETWORK, "map_betweenness_mean.png")
qmap(g, "aspl_mean",        "Mean shortest path length (meters)",   DIR_NETWORK, "map_aspl_mean.png")

# 2) MAPS — ACS outcomes
qmap(g, "owner_pct", "Owner-occupied share (%)", DIR_OUTCOME, "map_owner_pct_final.png")
qmap(g, "vac_rate",  "Vacancy rate (%)",         DIR_OUTCOME, "map_vac_rate_final.png")
qmap(g, "black_pct", "Black population (%)",     DIR_OUTCOME, "map_black_pct_final.png")

# 3) SCATTERS — relationships from your proposal
scatter("node_density", "owner_pct",
        "Owner share vs Node density", DIR_SCATTER, "scatter_owner_node_density.png",
        xlabel="Node density (nodes / km²)", ylabel="Owner-occupied share (%)")

scatter("aspl_mean", "vac_rate",
        "Vacancy vs Mean shortest path length", DIR_SCATTER, "scatter_vac_aspl.png",
        xlabel="Mean shortest path length (m)", ylabel="Vacancy rate (%)")

scatter("betweenness_mean", "owner_pct",
        "Owner share vs Betweenness (mean)", DIR_SCATTER, "scatter_owner_betweenness.png",
        xlabel="Betweenness (mean, nodes)", ylabel="Owner-occupied share (%)")

print("Maps and plots written to:", os.path.abspath(OUTDIR_BASE))
