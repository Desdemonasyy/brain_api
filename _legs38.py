"""第三十八阶段：路径 B —— 纯价格因子深化（pv1 数据源，与 fundamental6 完全正交）。

已确认通过的价格腿：
- ts_corr(close, volume, 20) 反向 → S-0.95（腿存在，方向正确）
- STD_VOL20 = ts_std_dev(volume,20)/ts_mean(volume,20) 反向 → S0.96

优化方向：
B1: ts_corr 深化（换窗口 60/120 + group_rank + 不同中性化）
B2: ts_corr + STD_VOL 组合（两个 pv1 腿，IC 预期低相关）
B3: ts_corr 加基本面低换手腿（pv1 + fundamental6，真正跨源）
B4: ts_corr + 另一个确认腿（反转）

关键约束：腿间 IC 必须低（数据源不同 → 真正正交 → √n 成立）。
"""
import csv, time
from datetime import datetime
import brain

BASE = {"neutralization": "SUBINDUSTRY", "decay": 10, "universe": "TOP3000", "truncation": 0.02}

# ------ 确认存在的算子 + 已确认有效的腿 ------
# ts_corr 存在，ts_std_dev 存在，ts_mean 存在，group_rank 存在

# ts_corr 腿（价量相关，价升量跌 → 后续反转）
CORR_NEG = "group_rank(-ts_corr(close, volume, {W}), {G})"   # 价量负相关反向

# STD_VOL 腿（成交量波动低 → 流动性好 → 后续好）
STD_VOL_NEG = "group_rank(-ts_std_dev(volume, {W}) / ts_mean(volume, {W}), {G})"

# fundamental6 低换手腿（已确认有效但之前没用到新组合）
# liabilities/assets（总负债率）—— docs/12 Top 5 通过字段之一
LEV = "group_rank(ts_rank(liabilities / assets, 126), sector)"

# pv1 反转腿（池内已通过，数据源不同）
REV5 = "group_rank(-ts_rank(close / lag(close, 5), 60), sector)"

# ------ B 系列组合 ------
BSERIES = [
    # === 第一组：ts_corr 单腿深化（找最优窗口 + 最优 group）===
    ("B1_corr20_subind", CORR_NEG.format(W=20, G="subindustry"), {"decay": 10}),
    ("B1b_corr60_subind", CORR_NEG.format(W=60, G="subindustry"), {"decay": 10}),
    ("B1c_corr120_subind", CORR_NEG.format(W=120, G="subindustry"), {"decay": 10}),
    ("B1d_corr20_sector", CORR_NEG.format(W=20, G="sector"), {"decay": 10}),
    ("B1e_corr60_sector", CORR_NEG.format(W=60, G="sector"), {"decay": 10}),
    ("B1f_corr20_decay20", CORR_NEG.format(W=20, G="subindustry"), {"decay": 20}),
    ("B1g_corr60_decay20", CORR_NEG.format(W=60, G="subindustry"), {"decay": 20}),

    # === 第二组：ts_corr + STD_VOL（两个 pv1 腿，数据源相同但统计量不同）===
    ("B2a_corr20_vol20", 
     f"{CORR_NEG.format(W=20, G='subindustry')} + {STD_VOL_NEG.format(W=20, G='subindustry')}",
     {"decay": 10}),
    ("B2b_corr60_vol60",
     f"{CORR_NEG.format(W=60, G='subindustry')} + {STD_VOL_NEG.format(W=60, G='subindustry')}",
     {"decay": 10}),
    ("B2c_corr60_vol60_d20",
     f"{CORR_NEG.format(W=60, G='subindustry')} + {STD_VOL_NEG.format(W=60, G='subindustry')}",
     {"decay": 20}),

    # === 第三组：pv1 + fundamental6 真正跨源 ===
    ("B3a_corr20_lev",
     f"{CORR_NEG.format(W=20, G='sector')} + {LEV}",
     {"decay": 10}),
    ("B3b_corr60_lev",
     f"{CORR_NEG.format(W=60, G='sector')} + {LEV}",
     {"decay": 10}),

    # === 第四组：三条腿（两个 pv1 + 一个 fundamental6，验证 √n 真正成立）===
    ("B4_triplet",
     f"{CORR_NEG.format(W=60, G='sector')} + {STD_VOL_NEG.format(W=60, G='sector')} + {LEV}",
     {"decay": 10}),
    ("B4b_triplet_d20",
     f"{CORR_NEG.format(W=60, G='sector')} + {STD_VOL_NEG.format(W=60, G='sector')} + {LEV}",
     {"decay": 20}),
]


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请重新登录")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/legs38_{stamp}.csv"
    fields = ["name", "alpha_id", "sharpe", "fitness", "turnover", "returns", "fails"]
    rows = []

    def flush():
        with open(out, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)

    for i, (name, expr, over) in enumerate(BSERIES, 1):
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
            print(f'[{i}/{len(BSERIES)}] {name:22s} {aid} S={row["sharpe"]} F={row["fitness"]} '
                  f'T={row["turnover"]} R={row["returns"]} FAIL={bad}', flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(BSERIES)}] {name:22s} FAILED {str(e)[:130]}", flush=True)
            rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                         "turnover": "", "returns": "", "fails": "ERROR"})
        flush()
        time.sleep(1.5)

    ok = [r for r in rows
          if isinstance(r["sharpe"], (int, float)) and isinstance(r["fitness"], (int, float))]
    ok.sort(key=lambda r: r["sharpe"], reverse=True)
    print("\n=== 排序（腿间完全正交：pv1 vs fundamental6）===")
    for r in ok:
        print(f'{r["sharpe"]:6.2f}  F={r["fitness"]:<5} T={r["turnover"]:<7} '
              f'R={r["returns"]:<7} {r["name"]:22s} {r["alpha_id"]}  {r["fails"]}')
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
