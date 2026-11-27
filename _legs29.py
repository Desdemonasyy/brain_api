"""第二十九阶段：非盈利维度的新字段（商誉/应付/股息/beta/无形资产等）。"""
import csv
import time
from datetime import datetime

import brain

s = brain.load()
if not brain.authenticated(s):
    print("cookie 失效，请重新登录")
    raise SystemExit(1)

BASE = "https://api.worldquantbrain.com"
PROBE = [
    "goodwill", "intangibles", "ppe", "inventory", "payable", "receivable",
    "assets", "sales", "equity", "debt", "dividend",
    "beta_250", "beta_60", "residvol_250", "residual_volatility",
    "scl8_buzz", "scl8_sentiment", "scl8_volume", "scl8_score",
]
print("=== 字段存在性 ===")
have = {}
for fid in PROBE:
    try:
        r = s.get(f"{BASE}/data-fields/{fid}",
                  headers={"Accept": "application/json;version=2.0"}, timeout=45)
        if r.status_code == 200:
            d = r.json()
            print(f'OK   {fid:<22} {d.get("type",""):<7} {(d.get("description") or "")[:46]}',
                  flush=True)
            have[fid] = d
        else:
            print(f'{r.status_code:<4} {fid}', flush=True)
    except Exception as e:  # noqa: BLE001
        print(f'EXC  {fid} {str(e)[:50]}', flush=True)
    time.sleep(1.2)

# 按存在的字段组装 alpha
LEGS = []
if "goodwill" in have:
    LEGS.append(("D1_goodwill_assets", "rank(-ts_rank(goodwill / assets, 126))"))
    LEGS.append(("D5_goodwill_equity", "rank(-ts_rank(goodwill / equity, 126))"))
if "payable" in have:
    LEGS.append(("D2_payable_assets", "rank(ts_rank(payable / assets, 126))"))
if "dividend" in have:
    LEGS.append(("D3_div_yield", "rank(ts_rank(dividend / close, 252))"))
if "intangibles" in have:
    LEGS.append(("D6_intang_assets", "rank(-ts_rank(intangibles / assets, 126))"))
if "ppe" in have:
    LEGS.append(("D7_ppe_assets", "rank(-ts_rank(ppe / assets, 126))"))
if "inventory" in have:
    LEGS.append(("D8_inv_assets", "rank(-ts_rank(inventory / assets, 126))"))
if "beta_250" in have:
    LEGS.append(("D4_beta250", "rank(-ts_rank(beta_250, 126))"))
if "residvol_250" in have:
    LEGS.append(("D9_residvol", "rank(-ts_rank(residvol_250, 126))"))
if "scl8_buzz" in have:
    LEGS.append(("D10_scl8_buzz", "rank(ts_mean(scl8_buzz, 20))"))

print(f"\n=== 模拟 {len(LEGS)} 条 ===")
SET = {"neutralization": "SUBINDUSTRY", "decay": 10, "universe": "TOP3000"}
stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
out = f"results/legs29_{stamp}.csv"
fields = ["name", "alpha_id", "sharpe", "fitness", "turnover", "returns", "fails"]
rows = []


def flush():
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


for i, (name, expr) in enumerate(LEGS, 1):
    try:
        sim_id, ra = brain.simulate(s, expr, **SET)
        time.sleep(ra)
        d = brain.wait(s, sim_id, timeout=520)
        aid = d.get("alpha")
        a = s.get(f"{BASE}/alphas/{aid}",
                  headers={"Accept": "application/json;version=2.0"}, timeout=60).json()
        st = a.get("is") or {}
        bad = [c["name"] for c in st.get("checks", []) if c.get("result") == "FAIL"]
        row = {"name": name, "alpha_id": aid, "sharpe": st.get("sharpe"),
               "fitness": st.get("fitness"), "turnover": st.get("turnover"),
               "returns": st.get("returns"), "fails": "|".join(bad)}
        rows.append(row)
        print(f'[{i}/{len(LEGS)}] {name:20s} {aid} S={row["sharpe"]} F={row["fitness"]} '
              f'T={row["turnover"]} R={row["returns"]} FAIL={bad}', flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"[{i}/{len(LEGS)}] {name:20s} FAILED {str(e)[:130]}", flush=True)
        rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                     "turnover": "", "returns": "", "fails": "ERROR"})
    flush()
    time.sleep(2)

print(f"\n结果已保存: {out}")
