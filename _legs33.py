"""第三十三阶段：弱腿组合的新结构探索。

V1（弱腿加法）R3.6% / F0.70，数学上限是因为等权稀释。
本批换乘法门控、集中持仓、极弱低换手腿三类新结构，
并加入 4 条未测弱腿候选。

核心目标：让弱腿组合的 Returns 从 3.6% 提到 7.4% 以上，
同时保持 Sharpe >= 1.25、T < 12.5%（Fitness 分母锁定）。
"""
import csv
import time
from datetime import datetime

import brain

CAPEX = "ts_rank(ts_backfill(anl4_capex_mean, 20) / sales, 126)"
INV = "ts_rank(inventory / assets, 126)"
REC = "ts_rank(ts_delta(receivable / sales, 252), 126)"
ACCR = "ts_rank((income - cashflow_op) / assets, 126)"

# ------ 新弱腿候选（未测）------
# 营运资金效率：sales / current_assets
WCEFF = "ts_rank(sales / current_assets, 126)"
# 资产增长反向（长窗口，G1 用的 63 日窗口太短）
ASTGRW = "ts_rank(ts_delta(assets, 252) / lag(assets, 252), 126)"
# 应收/资产 水平（不是变化率）
REC_ASSET = "ts_rank(receivable / assets, 126)"
# option9 看跌盈亏平衡折价（纯期权结构）
PUT_BE = "ts_rank(1 - ts_backfill(put_breakeven_120, 20) / close, 126)"
# pv13 客户图谱中心度（极低换手 ~0.77%）
PV13_CUST_PR = "pv13_ustomergraphrank_page_rank"

# ------ 组合方案 ------
# 1. 弱腿单腿先测，拿基线
LEGS = [
    ("T1_wceff", f"rank({WCEFF})", {}),
    ("T2_astgrw", f"rank(-{ASTGRW})", {}),
    ("T3_rec_asset", f"rank(-{REC_ASSET})", {}),
    ("T4_put_be", f"rank({PUT_BE})", {}),
    ("T5_pv13_cust", f"rank(-{PV13_CUST_PR})", {"decay": 4}),
]

# 2. 乘法门控：只有同时满足 capex低+存货低+应收低 的股票才有高权重
# rank 归一化后相乘，交集股票权重接近 1，其余接近 0
MUL1 = f"rank(-{CAPEX}) * rank(-{INV}) * rank(-{REC})"
MUL2 = f"rank(-{CAPEX}) * rank(-{INV})"
MUL3 = f"rank(-{CAPEX}) * rank(-{INV}) * rank(-{REC}) * rank(-{ACCR})"

# 3. 极弱低换手腿 + 中等弱腿（目标 T < 12.5% 锁定分母）
HYB1 = f"rank(-{CAPEX}) + rank({PV13_CUST_PR})"  # pv13 换手 0.77%，能拉低整体 T

# 4. 集中持仓（trunc 0.005）+ 加法弱腿（让少数股票贡献大收益）
ADD_CONC = f"-rank({CAPEX}) - rank({INV}) - rank({REC})"

# 5. 新弱腿组合
WNEW = f"rank({WCEFF}) + rank(-{ASTGRW}) + rank({PUT_BE})"

LEGS += [
    ("M1_mul3", MUL1, {"truncation": 0.02}),
    ("M2_mul2", MUL2, {"truncation": 0.02}),
    ("M3_mul4", MUL3, {"truncation": 0.02}),
    ("H1_pv13_inv", HYB1, {"truncation": 0.02, "decay": 10}),
    ("A1_conc", ADD_CONC, {"truncation": 0.005}),
    ("A2_conc_mul", MUL1, {"truncation": 0.005}),
    ("W1_new3", WNEW, {"truncation": 0.02}),
    ("M1_top1k", MUL1, {"truncation": 0.02, "universe": "TOP1000"}),
    ("M2_decay20", MUL2, {"truncation": 0.02, "decay": 20}),
]

BASE = {"neutralization": "SUBINDUSTRY", "decay": 10, "universe": "TOP3000",
        "truncation": 0.02}


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请重新登录")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/legs33_{stamp}.csv"
    fields = ["name", "alpha_id", "sharpe", "fitness", "turnover", "returns", "fails"]
    rows = []

    def flush():
        with open(out, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)

    for i, (name, expr, over) in enumerate(LEGS, 1):
        cfg = dict(BASE)
        cfg.update(over)
        try:
            sim_id, ra = brain.simulate(s, expr, **cfg)
            time.sleep(ra)
            d = brain.wait(s, sim_id, timeout=520)
            aid = d.get("alpha")
            a = s.get(f"https://api.worldquantbrain.com/alphas/{aid}",
                      headers={"Accept": "application/json;version=2.0"},
                      timeout=60).json()
            st = a.get("is") or {}
            bad = [c["name"] for c in st.get("checks", []) if c.get("result") == "FAIL"]
            row = {"name": name, "alpha_id": aid, "sharpe": st.get("sharpe"),
                   "fitness": st.get("fitness"), "turnover": st.get("turnover"),
                   "returns": st.get("returns"), "fails": "|".join(bad)}
            rows.append(row)
            print(f'[{i}/{len(LEGS)}] {name:16s} {aid} S={row["sharpe"]} F={row["fitness"]} '
                  f'T={row["turnover"]} R={row["returns"]} FAIL={bad}', flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(LEGS)}] {name:16s} FAILED {str(e)[:130]}", flush=True)
            rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                         "turnover": "", "returns": "", "fails": "ERROR"})
        flush()
        time.sleep(2)

    ok = [r for r in rows
          if isinstance(r["sharpe"], (int, float)) and isinstance(r["fitness"], (int, float))]
    ok.sort(key=lambda r: r["sharpe"], reverse=True)
    print("\n=== 按 Sharpe 排序（V1 基准 S1.30 F0.70 R3.6%）===")
    for r in ok:
        print(f'{r["sharpe"]:6.2f}  F={r["fitness"]:<5} T={r["turnover"]:<7} '
              f'R={r["returns"]:<7} {r["name"]:16s} {r["alpha_id"]}  {r["fails"]}')
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
