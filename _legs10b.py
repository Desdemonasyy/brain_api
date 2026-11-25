"""第十阶段修正：替换不可用算子 ts_max/ts_min，并简化可能溢出的表达式。"""
import csv
import time
from datetime import datetime

import brain

SUB = "SUBINDUSTRY"

LEGS = [
    # P2b 收益偏度（正偏 = 彩票特征，反向）
    ("P2b_skew",
     "rank(-ts_rank(ts_skewness(returns, 20), 126))",
     {"neutralization": SUB, "decay": 20}),
    # P4b 非流动性（纯成交量，去掉 *close 避免溢出）
    ("P4b_illiq",
     "rank(ts_rank(abs(returns) / (ts_mean(volume, 20) + 1), 126))",
     {"neutralization": SUB, "decay": 20}),
    # P5 异常成交量
    ("P5_abn_vol",
     "rank(-ts_rank(volume / ts_mean(volume, 60), 126))",
     {"neutralization": SUB, "decay": 20}),
    # P6 PCR 期限结构
    ("P6_pcr_term",
     "rank(ts_rank(pcr_oi_360 / pcr_oi_30, 126))",
     {"neutralization": SUB, "decay": 20}),
    # P8b 成交量水平（低流动性溢价）
    ("P8b_vol_lvl",
     "rank(-ts_rank(ts_mean(volume, 20), 126))",
     {"neutralization": SUB, "decay": 20}),
]


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请重新登录")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/legs10b_{stamp}.csv"
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
            print(f'[{i}/{len(LEGS)}] {name:11s} {aid}  S={row["sharpe"]}  '
                  f'F={row["fitness"]}  T={row["turnover"]}  R={row["returns"]}  '
                  f'FAIL={bad}', flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(LEGS)}] {name:11s} FAILED: {str(e)[:160]}", flush=True)
            rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                         "turnover": "", "returns": "", "fails": "ERROR"})
        flush()
        time.sleep(2)

    ok = [r for r in rows if isinstance(r["sharpe"], (int, float))]
    ok.sort(key=lambda r: r["sharpe"], reverse=True)
    print("\n=== 按 Sharpe 排序 ===")
    for r in ok:
        print(f'{r["sharpe"]:6.2f}  F={r["fitness"]:<5} T={r["turnover"]:<7} '
              f'{r["name"]:11s} {r["alpha_id"]}  {r["fails"]}')
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
