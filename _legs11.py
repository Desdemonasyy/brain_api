"""第十一阶段：低相关的结构来源 —— 残差、分层、乘法交互。

池内 11 条全部是「加法组合」+ 单调变换。本批改为：
  R1 残差反转：剥离市场 beta 后的特质收益反转
  R2 市值分层：bucket 分组，组内比较
  R3 行业动量：60 日行业相对强弱（与短期反转本质不同）
  R4-R6 乘法交互：只有两个信号同时强才入选，收益曲线形态与加法完全不同
"""
import csv
import time
from datetime import datetime

import brain

SUB = "SUBINDUSTRY"

LEGS = [
    # R1 残差反转（特质收益）
    ("R1_resid_rev",
     "-ts_rank(ts_regression(returns, group_mean(returns, market), 20, rettype=0), 126)",
     {"neutralization": "MARKET", "decay": 10}),
    # R2 市值分层反转
    ("R2_cap_bucket",
     'group_rank(-ts_rank(returns, 5), bucket(rank(cap), range="0,1,0.2"))',
     {"neutralization": "MARKET", "decay": 10}),
    # R3 行业动量（60 日）
    ("R3_ind_mom",
     "group_rank(ts_mean(returns, 60), industry)",
     {"neutralization": "MARKET", "decay": 10}),
    # R4 反转 × 低杠杆（乘法）
    ("R4_mul_rev_lev",
     "rank(-ts_rank(returns, 5)) * rank(-equity / assets)",
     {"neutralization": SUB, "decay": 10}),
    # R5 EBIT 收益率 × 低波（乘法）
    ("R5_mul_ebit_vol",
     "rank(ts_rank(anl4_ebit_value / cap, 126)) * rank(-ts_std_dev(returns, 20))",
     {"neutralization": SUB, "decay": 10}),
    # R6 量价背离 × 反转（乘法）
    ("R6_mul_pv_rev",
     "rank(-ts_corr(close, volume, 20)) * rank(-ts_rank(returns, 5))",
     {"neutralization": SUB, "decay": 10}),
]


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请重新登录")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/legs11_{stamp}.csv"
    fields = ["name", "alpha_id", "sharpe", "fitness", "turnover", "returns", "fails"]
    rows = []

    def flush():
        with open(out, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)

    for i, (name, expr, over) in enumerate(LEGS, 1):
        try:
            sim_id, retry_after = brain.simulate(s, expr, **over)
            time.sleep(retry_after)
            d = brain.wait(s, sim_id, timeout=420)
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
            print(f'[{i}/{len(LEGS)}] {name:15s} {aid}  S={row["sharpe"]}  '
                  f'F={row["fitness"]}  T={row["turnover"]}  R={row["returns"]}  '
                  f'FAIL={bad}', flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(LEGS)}] {name:15s} FAILED: {str(e)[:160]}", flush=True)
            rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                         "turnover": "", "returns": "", "fails": "ERROR"})
        flush()
        time.sleep(2)

    ok = [r for r in rows if isinstance(r["sharpe"], (int, float))]
    ok.sort(key=lambda r: r["sharpe"], reverse=True)
    print("\n=== 按 Sharpe 排序 ===")
    for r in ok:
        print(f'{r["sharpe"]:6.2f}  F={r["fitness"]:<5} T={r["turnover"]:<7} '
              f'{r["name"]:15s} {r["alpha_id"]}  {r["fails"]}')
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
