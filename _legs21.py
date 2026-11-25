"""第二十一阶段：深挖 J2（反转 + 前瞻E/P + IV）。

J2 基线：S2.03 / F1.38 / T53.13% / R24.59%（Returns 全池最高）
问题：换手 53% 使 Fitness 分母不锁定（>12.5%），F 被压到 1.38。

K 系列失败的教训：ts_rank(ts_mean(returns,5),60) 这种破坏性平滑抹掉了信号（S 从 2.03 掉到 0.86）。
本批改用 walk-forward 温和手段：
  - decay 提升（指数加权，只降权重变化速度）
  - truncation 收紧
  - 反转腿轻微平滑 ts_mean(returns,3)
  - 增加 ROE 质量腿提升 Sharpe
"""
import csv
import time
from datetime import datetime

import brain

FEP = "ts_rank(anl4_afv4_eps_mean / close, 126)"
ROE = "ts_rank(operating_income / equity, 126)"
IVL = "ts_backfill(implied_volatility_call_120 / parkinson_volatility_120, 20)"
REV = "ts_rank(returns, 5)"
REV3 = "ts_rank(ts_mean(returns, 3), 5)"


def j2(rev=REV, rev_w="", extra=""):
    return f"-{rev_w}rank({rev}) + rank({FEP}) + 0.5 * rank({IVL}){extra}"


LEGS = [
    ("L1_d10", j2(), {"neutralization": "MARKET", "decay": 10, "universe": "TOP1000"}),
    ("L2_d20", j2(), {"neutralization": "MARKET", "decay": 20, "universe": "TOP1000"}),
    ("L3_d15_tr05", j2(),
     {"neutralization": "MARKET", "decay": 15, "universe": "TOP1000", "truncation": 0.05}),
    ("L4_roe", j2(extra=f" + 0.5 * rank({ROE})"),
     {"neutralization": "MARKET", "decay": 10, "universe": "TOP1000"}),
    ("L5_rev15", j2(rev_w="1.5 * "),
     {"neutralization": "MARKET", "decay": 10, "universe": "TOP1000"}),
    ("L6_rev3", j2(rev=REV3),
     {"neutralization": "MARKET", "decay": 10, "universe": "TOP1000"}),
]


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请重新登录")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/legs21_{stamp}.csv"
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
    ok.sort(key=lambda r: r["fitness"] if isinstance(r["fitness"], (int, float)) else -9,
            reverse=True)
    print("\n=== 按 Fitness 排序（J2 基线 S2.03 F1.38 T53.13% R24.59%）===")
    for r in ok:
        print(f'{r["sharpe"]:6.2f}  F={r["fitness"]:<5} T={r["turnover"]:<7} '
              f'R={r["returns"]:<7} {r["name"]:12s} {r["alpha_id"]}  {r["fails"]}')
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
