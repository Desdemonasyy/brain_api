"""看涨-看跌隐含波动率价差（翻转方向）多期限验证。"""
import csv
import time
from datetime import datetime

import brain

TENORS = [30, 60, 90, 120, 180, 270]
SIGNALS = [
    (f"iv_call_minus_put_{t}",
     f"group_rank(implied_volatility_call_{t} - implied_volatility_put_{t}, subindustry)")
    for t in TENORS
]


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/ivskew_{stamp}.csv"
    fields = ["name", "alpha_id", "sharpe", "fitness", "turnover", "returns"]
    rows = []

    def flush():
        with open(out, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)

    for i, (name, expr) in enumerate(SIGNALS, 1):
        try:
            sim_id, retry_after = brain.simulate(s, expr)
            time.sleep(retry_after)
            d = brain.wait(s, sim_id)
            aid = d.get("alpha")
            a = s.get(f"https://api.worldquantbrain.com/alphas/{aid}",
                      headers={"Accept": "application/json;version=2.0"},
                      timeout=60).json()
            st = a.get("is") or {}
            row = {"name": name, "alpha_id": aid, "sharpe": st.get("sharpe"),
                   "fitness": st.get("fitness"), "turnover": st.get("turnover"),
                   "returns": st.get("returns")}
            rows.append(row)
            print(f'[{i}/{len(SIGNALS)}] {name:24s} {aid}  S={row["sharpe"]}  '
                  f'F={row["fitness"]}  T={row["turnover"]}  R={row["returns"]}', flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(SIGNALS)}] {name:24s} FAILED: {e}", flush=True)
            rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                         "turnover": "", "returns": ""})
        flush()
        time.sleep(2)

    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
