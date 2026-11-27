"""第二十五阶段：M3 精调，目标 F>3.0。

M3（rK0pjmM1，已提交）：S2.32 / F2.52 / T16.81% / R21.56%
关键：T=16.81% 刚超过 12.5% 锁定线。压到 12.5% 以下即得：
  F = 2.32 * sqrt(0.2156/0.125) = 3.05

对照 legprrG8（复合 Pyramid 当前占位者）：S2.24 / F2.60 / T10.88%
其 T 已锁定，要提 F 必须把 S 推到 2.58，难度更高。
所以本批以 M3 为基础做 decay/权重精调。
"""
import csv
import time
from datetime import datetime

import brain

FEP = "ts_rank(anl4_afv4_eps_mean / close, 126)"
ROE = "ts_rank(operating_income / equity, 126)"
IVL = "ts_backfill(implied_volatility_call_120 / parkinson_volatility_120, 20)"
REV = "ts_rank(returns, 5)"


def m3(roe_w="1.0", iv_w="0.5"):
    return (f"-rank({REV}) + rank({FEP}) + {iv_w} * rank({IVL})"
            f" + {roe_w} * rank({ROE})")


BASE = {"neutralization": "MARKET", "universe": "TOP1000"}

LEGS = [
    ("N1_d15", m3(), {**BASE, "decay": 15}),
    ("N2_d20", m3(), {**BASE, "decay": 20}),
    ("N3_d25", m3(), {**BASE, "decay": 25}),
    ("N4_d15_tr05", m3(), {**BASE, "decay": 15, "truncation": 0.05}),
    ("N5_d20_tr05", m3(), {**BASE, "decay": 20, "truncation": 0.05}),
    ("N6_d20_roe15", m3(roe_w="1.5"), {**BASE, "decay": 20}),
    ("N7_d20_iv10", m3(iv_w="1.0"), {**BASE, "decay": 20}),
    ("N8_d20_2k", m3(), {"neutralization": "MARKET", "universe": "TOP2000", "decay": 20}),
]


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请重新登录")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/legs25_{stamp}.csv"
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
            d = brain.wait(s, sim_id, timeout=480)
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
            print(f'[{i}/{len(LEGS)}] {name:13s} {aid}  S={row["sharpe"]}  '
                  f'F={row["fitness"]}  T={row["turnover"]}  R={row["returns"]}  '
                  f'FAIL={bad}', flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(LEGS)}] {name:13s} FAILED: {str(e)[:150]}", flush=True)
            rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                         "turnover": "", "returns": "", "fails": "ERROR"})
        flush()
        time.sleep(2)

    ok = [r for r in rows
          if isinstance(r["sharpe"], (int, float)) and isinstance(r["fitness"], (int, float))]
    ok.sort(key=lambda r: r["fitness"], reverse=True)
    print("\n=== 按 Fitness 排序（M3基线 S2.32 F2.52 T16.81%；目标 F>3.0）===")
    for r in ok:
        lock = "锁定" if isinstance(r["turnover"], (int, float)) and r["turnover"] <= 0.125 else "未锁"
        print(f'{r["sharpe"]:6.2f}  F={r["fitness"]:<5} T={r["turnover"]:<7}({lock}) '
              f'R={r["returns"]:<7} {r["name"]:13s} {r["alpha_id"]}  {r["fails"]}')
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
