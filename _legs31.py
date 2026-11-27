"""第三十一阶段：探查 model51/socialmedia8 字段 + W3 基础上优化。

W3（capex + 存货）S0.84 是本轮纯新维度上限。
弱腿协同规则：单腿 >=0.4 可协同，<0.2 是纯噪声。
可用的 >=0.4 腿：存货 0.77 / capex 0.46 / pcr_oi变化 0.87 / Q7 0.67
"""
import csv
import time
from datetime import datetime

import brain

s = brain.load()
if not brain.authenticated(s):
    print("cookie 失效，请重新登录")
    raise SystemExit(1)

BASE = "https://api.worldquantbrain.com"

# ---------- 1. 探查 model51 / socialmedia8 ----------
print("=== 探查 model51 / socialmedia8 ===")
found = {}
for ds in ["model51", "socialmedia8"]:
    d = None
    for a in range(3):
        r = s.get(f"{BASE}/data-fields?dataset.id={ds}&region=USA&delay=1"
                  f"&universe=TOP3000&limit=50",
                  headers={"Accept": "application/json;version=2.0"}, timeout=60)
        if r.status_code == 200:
            d = r.json()
            break
        print(f"  {ds} status={r.status_code}", flush=True)
        time.sleep(12 * (a + 1))
    if not d:
        continue
    print(f'\n[{ds}] 字段总数 {d.get("count")}')
    ids = []
    for f in d.get("results", []):
        fid = f.get("id")
        ids.append(fid)
        print(f'  {fid:<34} {f.get("type",""):<7} cov={f.get("coverage")} '
              f'users={f.get("alphaCount")}  {(f.get("description") or "")[:38]}')
    found[ds] = ids
    time.sleep(5)

# ---------- 2. W3 基础优化 ----------
CAPEX = "ts_rank(ts_backfill(anl4_capex_mean, 20) / sales, 126)"
INV = "ts_rank(inventory / assets, 126)"
PCR = "ts_delta(ts_backfill(pcr_oi_90, 20), 20)"
REC = "ts_rank(ts_delta(receivable / sales, 252), 126)"
EBITDA_Y = "ts_rank(ts_backfill(anl4_ebitda_value, 20) / cap, 126)"

W3 = f"-rank({CAPEX}) - rank({INV})"
V1 = f"-rank({CAPEX}) - rank({INV}) - rank({PCR})"
V4 = f"-rank({CAPEX}) - rank({INV}) - rank({PCR}) - rank({REC})"

LEGS = [
    ("V1_3leg", V1, {"decay": 10}),
    ("V2_3leg_d20", V1, {"decay": 20}),
    ("V3_3leg_t1k", V1, {"decay": 10, "universe": "TOP1000"}),
    ("V4_4leg", V4, {"decay": 10}),
    ("V5_inv15", f"-rank({CAPEX}) - 1.5 * rank({INV})", {"decay": 10}),
    ("V6_w3_ebitda", f"0.5 * ({W3}) + rank({EBITDA_Y})", {"decay": 10}),
]

# 若探到 model51/socialmedia8 字段，追加测试
for fid in found.get("model51", [])[:2]:
    LEGS.append((f"X_{fid[-12:]}", f"rank(-ts_rank({fid}, 126))", {"decay": 10}))
for fid in found.get("socialmedia8", [])[:2]:
    LEGS.append((f"X_{fid[-12:]}", f"rank(ts_mean({fid}, 20))", {"decay": 10}))

print(f"\n=== 模拟 {len(LEGS)} 条 ===")
stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
out = f"results/legs31_{stamp}.csv"
fields = ["name", "alpha_id", "sharpe", "fitness", "turnover", "returns", "fails"]
rows = []


def flush():
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


for i, (name, expr, over) in enumerate(LEGS, 1):
    cfg = {"neutralization": "SUBINDUSTRY", "decay": 10, "universe": "TOP3000"}
    cfg.update(over)
    try:
        sim_id, ra = brain.simulate(s, expr, **cfg)
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
        print(f'[{i}/{len(LEGS)}] {name:18s} {aid} S={row["sharpe"]} F={row["fitness"]} '
              f'T={row["turnover"]} R={row["returns"]} FAIL={bad}', flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"[{i}/{len(LEGS)}] {name:18s} FAILED {str(e)[:130]}", flush=True)
        rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                     "turnover": "", "returns": "", "fails": "ERROR"})
    flush()
    time.sleep(2)

ok = [r for r in rows
      if isinstance(r["sharpe"], (int, float)) and isinstance(r["fitness"], (int, float))]
ok.sort(key=lambda r: r["sharpe"], reverse=True)
print("\n=== 按 Sharpe 排序（W3 基准 0.84）===")
for r in ok:
    print(f'{r["sharpe"]:6.2f}  F={r["fitness"]:<5} T={r["turnover"]:<7} '
          f'R={r["returns"]:<7} {r["name"]:18s} {r["alpha_id"]}  {r["fails"]}')
print(f"\n结果已保存: {out}")
