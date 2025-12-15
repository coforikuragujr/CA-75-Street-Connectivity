# olsmodels.py
import pandas as pd
import statsmodels.api as sm

JOINED = r"outputs/tables/bg_joined.csv"
df = pd.read_csv(JOINED)

pairs = [
    ("owner_pct", "node_density"),
    ("vac_rate", "aspl_mean"),
    ("owner_pct", "betweenness_mean"),
]

for y, x in pairs:
    sub = df[[y, x]].apply(pd.to_numeric, errors="coerce").dropna()
    X = sm.add_constant(sub[x].values)
    yv = sub[y].values
    model = sm.OLS(yv, X).fit()
    print(f"\n=== {y} ~ {x} ===")
    print(model.summary().tables[1])
    print(f"R^2: {model.rsquared:.3f}   n={len(sub)}")
