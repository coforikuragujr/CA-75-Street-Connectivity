# computemetrics.py
# Compute network metrics for CA 75 (Morgan Park) and aggregate to block groups.
# Outputs: outputs/tables/bg_metrics.csv

import os
import math
import warnings
import pandas as pd
import geopandas as gpd
import networkx as nx
import osmnx as ox
from shapely.ops import unary_union

# Paths
GRAPHML = r"outputs/ca75_graph.graphml"
BG_GPKG = r"data/spatial/ca75_acs_bg_maps.gpkg"
LAYER   = "ca75_bg_acs"
OUT_TBLS = r"outputs/tables"
OUT_CSV  = os.path.join(OUT_TBLS, "bg_metrics.csv")

os.makedirs(OUT_TBLS, exist_ok=True)
warnings.filterwarnings("ignore", category=UserWarning)

# Helpers
def largest_component(G):
    UG = G.to_undirected()
    if nx.is_connected(UG):
        return G
    comp = max(nx.connected_components(UG), key=len)
    return G.subgraph(comp).copy()

def all_pairs_mean_shortest_path_length(G, weight="length"):
    """
    Return a dict: node -> mean weighted shortest-path length to all reachable nodes.
    Uses Dijkstra from each node; fine at this graph size (~500 nodes).
    """
    means = {}
    nodes = list(G.nodes())
    for u in nodes:
        lengths = nx.single_source_dijkstra_path_length(G, u, weight=weight)
        if len(lengths) > 1:
            # exclude self distance (0)
            s = sum(d for v, d in lengths.items() if v != u)
            means[u] = s / (len(lengths) - 1)
        else:
            means[u] = math.nan
    return means

def geodesic_to_metric(gdf, crs_metric=3857):
    """Project to a metric CRS for area/length calculations."""
    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    return gdf.to_crs(crs_metric)

# 1) Load graph and BG polygons
if not os.path.exists(GRAPHML):
    raise SystemExit(f"[FAIL] GraphML not found: {GRAPHML}")

G = ox.load_graphml(GRAPHML)
G = largest_component(G)

try:
    bg = gpd.read_file(BG_GPKG, layer=LAYER)
except Exception:
    bg = gpd.read_file(BG_GPKG)

if bg.empty:
    raise SystemExit(f"[FAIL] No BG geometries found in {BG_GPKG}")

# Ensure key
if "GEOID_BG" not in bg.columns:
    if "GEOID" in bg.columns:
        bg["GEOID_BG"] = bg["GEOID"].astype(str).str[-12:].str.zfill(12)
    else:
        raise SystemExit("[FAIL] BG layer lacks GEOID/GEOID_BG.")

# 2) Node/edge GeoDataFrames
nodes_gdf, edges_gdf = ox.graph_to_gdfs(G, nodes=True, edges=True)

# Guarantee a length attribute on edges
if "length" not in edges_gdf.columns:
    # compute from geometry if needed
    e_proj = geodesic_to_metric(edges_gdf)
    edges_gdf["length"] = e_proj.length.to_numpy()  # meters in projected CRS
else:
    # some graphs store length in meters already, keep as-is
    pass

# 3) Compute node metrics (betweenness, ASPL)
print("[INFO] Computing node betweenness (weighted by length)…")
btw = nx.betweenness_centrality(G, weight="length", normalized=True)
nx.set_node_attributes(G, btw, "betweenness")

print("[INFO] Computing node mean shortest path length (ASPL, weighted)…")
aspl = all_pairs_mean_shortest_path_length(G, weight="length")
nx.set_node_attributes(G, aspl, "aspl")

# Save back to GeoDataFrame
nodes_gdf["betweenness"] = nodes_gdf.index.map(btw)
nodes_gdf["aspl"] = nodes_gdf.index.map(aspl)

# 4) Aggregate to block groups
# Project to metric CRS for area/length
bg_m   = geodesic_to_metric(bg)
nodes_m = geodesic_to_metric(nodes_gdf)
edges_m = geodesic_to_metric(edges_gdf)

# BG area (km^2)
bg_m["area_km2"] = bg_m.geometry.area / 1_000_000.0

# Nodes within BG → counts and stats
nodes_in_bg = gpd.sjoin(nodes_m[["geometry","betweenness","aspl"]], bg_m[["GEOID_BG","geometry"]], predicate="within", how="left")
nodes_grp = nodes_in_bg.groupby("GEOID_BG").agg(
    nodes_in_bg=("geometry","count"),
    betweenness_mean=("betweenness","mean"),
    betweenness_p90=("betweenness", lambda s: s.quantile(0.90)),
    aspl_mean=("aspl","mean"),
).reset_index()

# Edges intersect BG → sum intersection length
# Intersect each edge with BGs, sum length in km per BG
inter = gpd.overlay(edges_m[["geometry","length"]], bg_m[["GEOID_BG","geometry"]], how="intersection")
# geometry is the clipped portion; compute length in meters then km
inter["len_km"] = inter.geometry.length / 1000.0
edges_grp = inter.groupby("GEOID_BG").agg(edges_km=("len_km","sum")).reset_index()

# Merge node/edge summaries with BG area
metrics = bg_m[["GEOID_BG","area_km2"]].merge(nodes_grp, on="GEOID_BG", how="left").merge(edges_grp, on="GEOID_BG", how="left")

# Densities
metrics["node_density"] = metrics["nodes_in_bg"] / metrics["area_km2"]
metrics["edge_km_density"] = metrics["edges_km"] / metrics["area_km2"]

# Clean up NaNs for empty joins
for c in ["nodes_in_bg","betweenness_mean","betweenness_p90","aspl_mean","edges_km","node_density","edge_km_density"]:
    if c in metrics.columns:
        metrics[c] = metrics[c].astype(float)

# 5) Write output
keep = ["GEOID_BG","area_km2","nodes_in_bg","edges_km","node_density","edge_km_density","betweenness_mean","betweenness_p90","aspl_mean"]
metrics[keep].to_csv(OUT_CSV, index=False)
print(f"[OK] Wrote metrics: {OUT_CSV}")
print("Metrics computed!")
