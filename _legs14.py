"""第十四阶段：X3 改中性化方式 —— 唯一能大幅降低 PnL 相关性的手段。

背景：
  9qGZbZ2o (X3_d3) 已提交：SUBINDUSTRY / decay 3 / TOP1000 -> S2.29 F2.22
  A1LjY3PE (X3_d4)：S2.26 无法提交（豁免线 2.519）

X3 表达式全是 rank 全市场排序，没有 group 操作，所以 Settings 的
neutralization 会真实生效，不会双重中性化。

换 universe 无效（TOP3000 与 TOP1000 重叠 33%，corr 仍 0.85+）。
改中性化能彻底改变行业/风格暴露 -> corr 预期降到 0.55-0.70。
"""
import csv
import time
from datetime import datetime

import brain

X3 = ("rank(ts_rank(anl4_ebit_value / cap, 126)) "
      "+ rank(ts_backfill(implied_volatility_call_120 / parkinson_volatility_120, 20)) "
      "+ 0.5 * rank(ts_rank(operating_income / equity, 126))")

LEGS = [
    ("X3_mkt_d3", X3, {"neutralization": "MARKET", "decay": 3, "universe": "TOP1000"}),
    ("X3_mkt_d5", X3, {"neutralization": "MARKET", "decay": 5, "universe": "TOP1000"}),
    ("X3_ind_d3", X3, {"neutralization": "INDUSTRY", "decay": 3, "universe": "TOP1000"}),
    ("X3_none_d3", X3, {"neutralization": "NONE", "decay": 3, "universe": "TOP1000"}),
]


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请重新登录")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/legs14_{stamp}.csv"
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
            print(f'[{i}/{len(LEGS)}] {name:12s} {aid}  S={row["sharpe"]}  '
                  f'F={row["fitness"]}  T={row["turnover"]}  R={row["returns"]}  '
                  f'FAIL={bad}', flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(LEGS)}] {name:12s} FAILED: {str(e)[:160]}", flush=True)
            rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                         "turnover": "", "returns": "", "fails": "ERROR"})
        flush()
        time.sleep(2)

    ok = [r for r in rows if isinstance(r["sharpe"], (int, float))]
    ok.sort(key=lambda r: r["sharpe"], reverse=True)
    print("\n=== 按 Sharpe 排序 ===")
    for r in ok:
        print(f'{r["sharpe"]:6.2f}  F={r["fitness"]:<5} T={r["turnover"]:<7} '
              f'{r["name"]:12s} {r["alpha_id"]}  {r["fails"]}')
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
