import requests, pandas as pd, time  # HTTP requests, tabular operations, retry sleep

# Fixed geography (Illinois / Cook County)
STATE, COUNTY = "17", "031"

# CA 75 tracts (2020 geography)
tracts = ["750100","750200","750300","750400","750500","750600"]

# ACS 5-year API endpoint (use 2022 or change to 2023 as needed)
API = "https://api.census.gov/data/2022/acs/acs5"  # or 2023

# Variables: total pop, race (white/black/asian), and tenure (owner/renter)
VARS = [
    "B01003_001E", # total pop
    "B02001_002E","B02001_003E","B02001_005E", # white, black, asian
    "B25003_002E","B25003_003E", # owner, renter
]

def fetch(tract):
    """Fetch block-group rows for one tract. Returns a DataFrame or None on failure."""
    params = {
        "get": ",".join(VARS + ["NAME"]),
        "for": "block group:*",
        "in": f"state:{STATE} county:{COUNTY} tract:{tract}"
    }
    # Two tries for transient errors
    for _ in range(2):
        r = requests.get(API, params=params, timeout=60)
        if r.status_code == 200:
            data = r.json()
            return pd.DataFrame([dict(zip(data[0], row)) for row in data[1:]])
        time.sleep(0.6)
    # If both tries fail, warn and move on
    print(f"[warn] {tract}: HTTP {r.status_code}"); return None

frames = []
for t in tracts:
    try:
        df = fetch(t)
        if df is not None: frames.append(df)
    except Exception as e:
        # Robust to odd network or parsing errors; continue with other tracts
        print(f"[warn] {t}: {e}")

# Stop early if nothing returned
if not frames:
    raise SystemExit("No data returned. Check API year or tract list.")

# Stack all block groups together
df = pd.concat(frames, ignore_index=True)

# Rename variables to concise names and force numeric types
ren = {
  "B01003_001E":"pop",
  "B02001_002E":"white","B02001_003E":"black","B02001_005E":"asian",
  "B25003_002E":"owner","B25003_003E":"renter"
}
df = df.rename(columns=ren)
for c in ren.values(): df[c] = pd.to_numeric(df[c], errors="coerce")

# Construct IDs for later joins (tract, block group, full 12-digit GEOID)
df["TRACT"] = df["tract"].str.zfill(6)
df["BG"] = df["block group"]
df["GEOID_BG"] = "17031" + df["TRACT"] + df["BG"]

# Compute basic rates: race shares and owner share
df["white_pct"] = (df["white"]/df["pop"]*100).round(2)
df["black_pct"] = (df["black"]/df["pop"]*100).round(2)
df["asian_pct"] = (df["asian"]/df["pop"]*100).round(2)
df["owner_pct"] = (df["owner"]/(df["owner"]+df["renter"])*100).round(2)

# Save for mapping/analysis in later deliverables
df.to_csv("ca75_acs_blockgroups.csv", index=False)
print("Wrote ca75_acs_blockgroups.csv")
