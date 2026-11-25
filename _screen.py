"""单信号筛查：批量模拟候选表达式，按 Sharpe 排序，找 >=1.8 的新信号。"""
import csv
import time
from datetime import datetime

import requests

import brain

API = "https://api.worldquantbrain.com"
H = {"Accept": "application/json;version=2.0"}

SIGNALS = [
    ("close_in_range", "-group_zscore(if_else(high > low, (close - low) / (high - low) - 0.5, 0), subindustry)"),
    ("vwap_dev", "-group_zscore((vwap - close) / vwap, subindustry)"),
    ("volw_rev", "-group_zscore((close - open) / open * rank(volume), subindustry)"),
    ("volscaled_rev", "-group_zscore((close - open) / open / ts_std_dev(returns, 20), subindustry)"),
    ("rev_2d_skip", "-group_zscore(ts_delay(close, 1) / ts_delay(close, 3) - 1, subindustry)"),
    ("rev_10d_skip", "-group_zscore(ts_delay(close, 1) / ts_delay(close, 10) - 1, subindustry)"),
    ("news_5d", "group_rank(ts_mean(vec_avg(nws12_afterhsz_sl), 5), subindustry)"),
    ("upper_shadow", "-group_zscore(ts_mean((high - close) / close, 5), subindustry)"),
    ("lower_shadow", "-group_zscore(ts_mean((close - low) / close, 5), subindustry)"),
    ("vwap_change", "-group_zscore(ts_delta(vwap, 1) / vwap, subindustry)"),
    ("turnover_5d", "group_zscore(ts_mean(volume / cap, 5), subindustry)"),
    ("vol_regime", "-group_zscore(ts_std_dev(returns, 5) / ts_std_dev(returns, 60), subindustry)"),
    ("ctrl_intraday_rev", "-group_zscore((close - open) / open, subindustry)"),
]


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请先运行: python login_playwright.py")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/screen_{stamp}.csv"
    rows = []
    for i, (name, expr) in enumerate(SIGNALS, 1):
        try:
            sim_id, retry_after = brain.simulate(s, expr)
            time.sleep(retry_after)
            d = brain.wait(s, sim_id)
            aid = d.get("alpha")
            a = s.get(f"{API}/alphas/{aid}", headers=H, timeout=60).json()
            st = a.get("is") or {}
            row = {
                "name": name,
                "alpha_id": aid,
                "sharpe": st.get("sharpe"),
                "fitness": st.get("fitness"),
                "turnover": st.get("turnover"),
                "returns": st.get("returns"),
            }
            rows.append(row)
            print(
                f'[{i}/{len(SIGNALS)}] {name:20s} {aid}  '
                f'S={row["sharpe"]}  F={row["fitness"]}  T={row["turnover"]}',
                flush=True,
            )
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(SIGNALS)}] {name:20s} FAILED: {e}", flush=True)
            rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                         "turnover": "", "returns": ""})
        time.sleep(2)

    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["name", "alpha_id", "sharpe", "fitness", "turnover", "returns"])
        w.writeheader()
        w.writerows(rows)

    ok = [r for r in rows if isinstance(r["sharpe"], (int, float))]
    ok.sort(key=lambda r: r["sharpe"], reverse=True)
    print("\n=== 按 Sharpe 排序 ===")
    for r in ok:
        print(f'{r["sharpe"]:6.2f}  {r["name"]:20s} {r["alpha_id"]}  F={r["fitness"]}  T={r["turnover"]}')
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
