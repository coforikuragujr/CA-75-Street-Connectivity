# buildnetwork.py
# Build a drivable street network for Community Area 75 (Morgan Park) using OSMnx.
# Compatible with older OSMnx versions (no 'clean_periphery' kwarg).

import os
import warnings

import geopandas as gpd
import matplotlib.pyplot as plt
import networkx as nx
import osmnx as ox
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union

# -------------------------
# Paths (relative to your final_project folder)
# -------------------------
BG_GPKG   = r"data/spatial/ca75_acs_bg_maps.gpkg"  # from HW4
LAYER     = "ca75_bg_acs"                          # layer name you wrote in deliverable3
OUT_DIR   = r"outputs"
OUT_TBLS  = os.path.join(OUT_DIR, "tables")
OUT_FIGS  = os.path.join(OUT_DIR, "figures")
GRAPHML   = os.path.join(OUT_DIR, "ca75_graph.graphml")
NODES_CSV = os.path.join(OUT_TBLS, "nodes.csv")
EDGES_CSV = os.path.join(OUT_TBLS, "edges.csv")
OVERVIEW  = os.path.join(OUT_FIGS, "ca75_graph_overview.png")

os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(OUT_TBLS, exist_ok=True)
os.makedirs(OUT_FIGS, exist_ok=True)

# Quiet noisy warnings
warnings.filterwarnings("ignore", category=UserWarning)
ox.settings.log_console = False
ox.settings.use_cache = True


def dissolve_to_single_polygon(gdf: gpd.GeoDataFrame) -> Polygon | MultiPolygon:
    """Dissolve a GeoDataFrame of BG polygons to a single CA boundary polygon."""
    gdf = gdf[~gdf.geometry.is_empty & gdf.geometry.notna()].copy()
    # Project to meters to smooth tiny artifacts
    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    gproj = gdf.to_crs(3857)
    geom_proj = unary_union(gproj.geometry.values)
    geom_proj = geom_proj.buffer(50).buffer(-50)  # smooth slivers (meters)
    ca_geom = gpd.GeoSeries([geom_proj], crs=3857).to_crs(4326).iloc[0]
    return ca_geom


def get_drive_graph(poly):
    """
    Compatibility wrapper for different OSMnx versions.
    Tries newer signature first, then falls back to older ones.
    """
    base_kwargs = dict(network_type="drive", simplify=True, retain_all=False)
    # Newer OSMnx (has clean_periphery)
    try:
        return ox.graph_from_polygon(poly, **base_kwargs, clean_periphery=True)
    except TypeError:
        pass
    # Mid/older OSMnx (no clean_periphery kwarg)
    try:
        return ox.graph_from_polygon(poly, **base_kwargs)
    except TypeError:
        pass
    # Very old OSMnx (positional args)
    return ox.graph_from_polygon(poly, "drive", True, False)


def largest_connected_component(G):
    """Keep the largest connected component (standard for analysis)."""
    UG = G.to_undirected()
    if nx.is_connected(UG):
        return G
    comp = max(nx.connected_components(UG), key=len)
    return G.subgraph(comp).copy()


def main():
    # 1) Read BG polygons from your HW4 GeoPackage (fallback: read without layer)
    try:
        bg = gpd.read_file(BG_GPKG, layer=LAYER)
    except Exception:
        bg = gpd.read_file(BG_GPKG)
    if bg.empty:
        raise SystemExit(f"[FAIL] No geometries found in {BG_GPKG}")

    # 2) Dissolve BGs to one CA 75 polygon (WGS84 for OSMnx)
    if bg.crs is None:
        bg = bg.set_crs(4326)
    ca75_poly = dissolve_to_single_polygon(bg)
    if ca75_poly is None or ca75_poly.is_empty:
        raise SystemExit("[FAIL] Could not dissolve BGs into a single CA polygon.")

    # 3) Download a drivable street graph within the polygon
    print("[INFO] Downloading drivable network from OSM …")
    G = get_drive_graph(ca75_poly)

    # If graph is empty (rare), expand polygon slightly and retry
    if len(G.nodes) == 0:
        print("[WARN] Graph came back empty; expanding boundary slightly and retrying.")
        ca_buff = gpd.GeoSeries([ca75_poly], crs=4326).to_crs(3857).buffer(150).to_crs(4326).iloc[0]
        G = get_drive_graph(ca_buff)
        if len(G.nodes) == 0:
            raise SystemExit("[FAIL] Still empty after buffering; check boundary or internet connection.")

    # Keep only the largest connected component
    G = largest_connected_component(G)

    # 4) Save GraphML for reuse
    ox.save_graphml(G, GRAPHML)
    print(f"[OK] Saved graph: {GRAPHML}  (nodes={len(G.nodes)}, edges={len(G.edges)})")

    # 5) Export node/edge tables for later aggregation to BG
    nodes, edges = ox.graph_to_gdfs(G, nodes=True, edges=True)
    node_keep = [c for c in ["osmid", "x", "y"] if c in nodes.columns]
    edge_keep = [c for c in ["u", "v", "length", "highway", "name"] if c in edges.columns]
    nodes[node_keep].to_csv(NODES_CSV, index=False)
    edges[edge_keep].to_csv(EDGES_CSV, index=False)
    print(f"[OK] Wrote node table: {NODES_CSV}")
    print(f"[OK] Wrote edge table: {EDGES_CSV}")

    # 6) Quick overview plot to confirm extent
    fig, ax = plt.subplots(1, 1, figsize=(8, 8))
    edges.to_crs(3857).plot(ax=ax, linewidth=0.6, alpha=0.8)
    gpd.GeoSeries([ca75_poly], crs=4326).to_crs(3857).boundary.plot(ax=ax, color="black", linewidth=1.2)
    ax.set_axis_off()
    ax.set_title("CA 75 Drivable Network — Overview")
    plt.tight_layout()
    plt.savefig(OVERVIEW, dpi=200)
    plt.close()
    print(f"[OK] Saved overview map: {OVERVIEW}")

    print("Network build complete!")

if __name__ == "__main__":
    main()
