import requests, pandas as pd, time  # HTTP requests, tabular data, simple retry timing

# Fixed geography (Illinois / Cook County)
STATE = "17"
COUNTY = "031"

# Tract lists for CA 75 (2020 set excludes 750700 which existed in 2010)
tracts_2020 = ["750100","750200","750300","750400","750500","750600"]
tracts_2010 = ["750100","750200","750300","750400","750500","750600","750700"]

def fetch_census(api, vars_, tracts):
    """Fetch all block groups for a list of tracts; skip any tract that 400s; return one DataFrame."""
    frames = []
    for t in tracts:
        # Build API parameters for one tract at a time
        params = {
            "get": ",".join(vars_ + ["NAME"]),
            "for": "block group:*",
            "in": f"state:{STATE} county:{COUNTY} tract:{t}"
        }
        # Small two-try loop to handle transient errors
        for attempt in range(2):
            r = requests.get(api, params=params, timeout=60)
            if r.status_code == 200:
                data = r.json()
                cols = data[0]
                rows = [dict(zip(cols, rec)) for rec in data[1:]]
                df = pd.DataFrame(rows)
                frames.append(df)
                break
            else:
                # brief pause, then retry once
                time.sleep(0.7)
        else:
            # If both attempts fail, warn and continue to next tract
            print(f"[warn] Skipping tract {t} (HTTP {r.status_code}). URL was: {r.url}")
    if not frames:
        return pd.DataFrame()
    # Combine block groups and standardize IDs
    df = pd.concat(frames, ignore_index=True)
    df["TRACT"] = df["tract"].str.zfill(6)
    df["BG"] = df["block group"]
    df["GEOID_BG"] = "17031" + df["TRACT"] + df["BG"]
    return df

def main():
    # ---------------- 2020 PL (block-group) ----------------
    # Variables: total population + race + Hispanic table denominator/estimate
    api20 = "https://api.census.gov/data/2020/dec/pl"
    vars20 = ["P1_001N","P1_003N","P1_004N","P1_006N","P2_001N","P2_002N"]
    df20 = fetch_census(api20, vars20, tracts_2020).rename(columns={
        "P1_001N":"pop20",      # Total population
        "P1_003N":"white20",
        "P1_004N":"black20",
        "P1_006N":"asian20",
        "P2_001N":"p2tot20",    # total for Hispanic table
        "P2_002N":"hisp20"
    })
    if not df20.empty:
        # Convert to numeric and compute 2020 percentages
        for c in ["pop20","white20","black20","asian20","p2tot20","hisp20"]:
            df20[c] = pd.to_numeric(df20[c], errors="coerce")
        df20["white20_pct"] = (df20["white20"]/df20["pop20"]*100).round(2)
        df20["black20_pct"] = (df20["black20"]/df20["pop20"]*100).round(2)
        df20["asian20_pct"] = (df20["asian20"]/df20["pop20"]*100).round(2)
        df20["hisp20_pct"]  = (df20["hisp20"]/df20["p2tot20"]*100).round(2)
        df20.to_csv("morgan_park_ca75_2020_blockgroups.csv", index=False)

    # ---------------- 2010 SF1 (block-group) ----------------
    # Variables: total population + race + Hispanic table denominator/estimate
    api10 = "https://api.census.gov/data/2010/dec/sf1"
    vars10 = ["P001001","P005003","P005004","P005006","P004001","P004003"]
    df10 = fetch_census(api10, vars10, tracts_2010).rename(columns={
        "P001001":"pop10",      # Total population
        "P005003":"white10",
        "P005004":"black10",
        "P005006":"asian10",
        "P004001":"p4tot10",    # total for Hispanic table
        "P004003":"hisp10"
    })
    if not df10.empty:
        # Convert to numeric and compute 2010 percentages
        for c in ["pop10","white10","black10","asian10","p4tot10","hisp10"]:
            df10[c] = pd.to_numeric(df10[c], errors="coerce")
        df10["white10_pct"] = (df10["white10"]/df10["pop10"]*100).round(2)
        df10["black10_pct"] = (df10["black10"]/df10["pop10"]*100).round(2)
        df10["asian10_pct"] = (df10["asian10"]/df10["pop10"]*100).round(2)
        df10["hisp10_pct"]  = (df10["hisp10"]/df10["p4tot10"]*100).round(2)
        df10.to_csv("morgan_park_ca75_2010_blockgroups.csv", index=False)

    # ---------------- Merge & compute change ----------------
    # Only proceed if both years are available
    if not df10.empty and not df20.empty:
        keep20 = ["GEOID_BG","TRACT","BG","pop20","white20","black20","asian20","hisp20","white20_pct","black20_pct","asian20_pct","hisp20_pct"]
        keep10 = ["GEOID_BG","TRACT","BG","pop10","white10","black10","asian10","hisp10","white10_pct","black10_pct","asian10_pct","hisp10_pct"]
        merged = pd.merge(df10[keep10], df20[keep20], on=["TRACT","BG"], how="outer")

        # Helper for percent change with divide-by-zero/NA protection
        def pct_change(new, old):
            try:
                new = float(new); old = float(old)
                if old == 0: return None
                return round((new - old) / old * 100.0, 2)
            except: return None

        # Absolute change and percent change for selected numerators
        for numer in ["pop","white","black","asian","hisp"]:
            merged[f"{numer}_chg"] = merged[f"{numer}20"] - merged[f"{numer}10"]
            merged[f"{numer}_chg_pct"] = [pct_change(n, o) for n, o in zip(merged[f"{numer}20"], merged[f"{numer}10"])]

        merged.to_csv("morgan_park_ca75_2010_2020_comparison.csv", index=False)
        print("Wrote morgan_park_ca75_2010_2020_comparison.csv")

if __name__ == "__main__":
    main()
