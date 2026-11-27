"""探查 analyst4 更多预期类字段，并对存在的字段直接跑验证。"""
import csv
import time
from datetime import datetime

import brain

s = brain.load()
if not brain.authenticated(s):
    print("cookie 失效，请重新登录")
    raise SystemExit(1)

BASE = "https://api.worldquantbrain.com"
CAND = [
    "anl4_ebit_mean", "anl4_ebitda_value", "anl4_fcf_value",
    "anl4_capex_mean", "anl4_revenue_mean", "anl4_gross_income_mean",
    "anl4_eps_median", "anl4_eps_high", "anl4_eps_low",
    "anl4_num_estimates", "anl4_cashflow_mean", "anl4_dividend_mean",
    "anl4_ebitda_median", "anl4_fcf_median", "anl4_eps_std",
    "anl4_ebitda_number", "anl4_fcf_number",
]

print("=== 字段存在性 ===")
have = []
for fid in CAND:
    try:
        r = s.get(f"{BASE}/data-fields/{fid}",
                  headers={"Accept": "application/json;version=2.0"}, timeout=45)
        if r.status_code == 200:
            d = r.json()
            print(f'OK   {fid:<26} {(d.get("description") or "")[:50]}', flush=True)
            have.append(fid)
        else:
            print(f'{r.status_code:<4} {fid}', flush=True)
    except Exception as e:  # noqa: BLE001
        print(f'EXC  {fid} {str(e)[:50]}', flush=True)
    time.sleep(1.2)

# 对确认存在的字段跑验证
LEGS = [
    ("EBITDA_yield", "rank(ts_rank(anl4_ebitda_mean / cap, 126))"),
    ("FCF_yield", "rank(ts_rank(anl4_fcf_mean / cap, 126))"),
    ("EBITDA_margin", "rank(ts_rank(anl4_ebitda_mean / sales, 126))"),
    ("EBITDA_FCF_combo",
     "rank(ts_rank(anl4_ebitda_mean / cap, 126)) + rank(ts_rank(anl4_fcf_mean / cap, 126))"),
]
for fid in have:
    if fid not in ("anl4_ebitda_mean", "anl4_fcf_mean"):
        LEGS.append((f"yield_{fid[5:]}", f"rank(ts_rank({fid} / cap, 126))"))

SET = {"neutralization": "SUBINDUSTRY", "decay": 10, "universe": "TOP3000"}
print(f"\n=== 模拟 {len(LEGS)} 条 ===")
stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
out = f"results/legs27_{stamp}.csv"
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
        d = brain.wait(s, sim_id, timeout=480)
        aid = d.get("alpha")
        a = s.get(f"{BASE}/alphas/{aid}",
                  headers={"Accept": "application/json;version=2.0"}, timeout=60).json()
        st = a.get("is") or {}
        bad = [c["name"] for c in st.get("checks", []) if c.get("result") == "FAIL"]
        row = {"name": name, "alpha_id": aid, "sharpe": st.get("sharpe"),
               "fitness": st.get("fitness"), "turnover": st.get("turnover"),
               "returns": st.get("returns"), "fails": "|".join(bad)}
        rows.append(row)
        print(f'[{i}/{len(LEGS)}] {name:18s} {aid} S={row["sharpe"]} F={row["fitness"]} '
              f'T={row["turnover"]} R={row["returns"]} FAIL={bad}', flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"[{i}/{len(LEGS)}] {name:18s} FAILED {str(e)[:120]}", flush=True)
        rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                     "turnover": "", "returns": "", "fails": "ERROR"})
    flush()
    time.sleep(2)

print(f"\n结果已保存: {out}")
