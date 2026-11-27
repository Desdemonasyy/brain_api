"""第三十四阶段：弱腿组合的社区技巧验证。

从 HalleyTech 社区文章中提取的关键设置：
1. truncation 0.05-0.1（我之前一直用 0.01-0.04）
2. 条件门控表达式（三元运算符 trade_when）
3. 表达式内中性化（group_rank 已用，但 group_vector_neut / vector_neut 未用）
4. 弱腿需 IC > ρ×IC_book 才能有正权重，否则是对冲

成功案例参考：
- buzz 情绪：trunc 0.1, decay 5, S1.94, T44.52%
- 条件门控 + 新闻：decay 30, S1.84, T8.99%
- EBIT/capex：trunc 0.01, decay 10, S1.62, T2.21% (极低换手)
"""
import csv
import time
from datetime import datetime

import brain

# ------ 核心弱腿 ------
CAPEX = "ts_rank(ts_backfill(anl4_capex_mean, 20) / sales, 126)"
INV = "ts_rank(inventory / assets, 126)"
REC = "ts_rank(ts_delta(receivable / sales, 252), 126)"
ACCR = "ts_rank((income - cashflow_op) / assets, 126)"

# ------ 新弱腿候选 ------
# 低换手弱腿（参考 EBIT/capex S1.62 T2.21%）
EBIT_CAPEX = "ts_rank(ts_backfill(anl4_ebit_value, 20) / ts_backfill(anl4_capex_mean, 20), 126)"
# 营运资金周转率低 = 效率低
WCTURN = "ts_rank(sales / (current_assets - current_liabilities), 126)"
# 应收/资产（水平）
REC_ASSET = "ts_rank(receivable / assets, 126)"
# 现金流利润率（vs ACCR 的应计利润率）
CF_MARGIN = "ts_rank(cashflow_op / sales, 126)"

# ------ 组合方案 ------
# A: 简单加法 + trunc 0.05（之前用 0.02）
A1 = f"-rank({CAPEX}) - rank({INV}) - rank({REC})"
A2 = f"-rank({CAPEX}) - rank({INV}) - rank({REC}) - rank({ACCR})"
A3 = f"-rank({CAPEX}) - rank({INV}) + rank({CF_MARGIN})"

# B: 条件门控（参考文章 "rank(ts_sum(news,60)) > 0.5 ? 1 : rank(-rev)"）
# 只有当 capex 排名低（过度投资）时，才激活存货因子
B1 = f"rank({CAPEX}) < 0.3 ? -rank({INV}) : 0"
# 只有当应计排名高时，才激活现金流因子
B2 = f"rank({ACCR}) > 0.7 ? rank({CF_MARGIN}) : 0"
# 双条件门控
B3 = f"(rank({CAPEX}) < 0.3) & (rank({INV}) < 0.3) ? -1 : 0"

# C: EBIT/capex 比例腿（参考文章 S1.62 T2.21% 低换手）
C1 = f"rank({EBIT_CAPEX})"  # 单独验证
C2 = f"rank({EBIT_CAPEX}) + rank({CF_MARGIN})"  # 双低腿

# D: 之前 V1 的优化（加法弱腿 + trunc 0.05 + TOP2000）
D1 = A1
D2 = A1

# E: 全新三元组合（CAPEX反向 + REC反向 + CF_MARGIN正向）
E1 = f"-rank({CAPEX}) - rank({REC}) + rank({CF_MARGIN})"

# 批量配置
# 默认用 trunc 0.05（参考社区最佳值）
CONFIGS = [
    ("A1_add3_t005", A1, {"truncation": 0.05, "decay": 10}),
    ("A2_add4_t005", A2, {"truncation": 0.05, "decay": 10}),
    ("A3_capex_inv_cf", A3, {"truncation": 0.05, "decay": 10}),
    ("B1_gate_inv", B1, {"truncation": 0.05, "decay": 10}),
    ("B2_gate_cf", B2, {"truncation": 0.05, "decay": 10}),
    ("B3_gate_both", B3, {"truncation": 0.05, "decay": 10}),
    ("C1_ebit_capex", C1, {"truncation": 0.01, "decay": 10}),
    ("C2_ebit_capex_cf", C2, {"truncation": 0.01, "decay": 10}),
    ("D1_v1_t005", D1, {"truncation": 0.05, "decay": 10}),
    ("D2_v1_t01", D2, {"truncation": 0.1, "decay": 10}),
    ("E1_triplet_t005", E1, {"truncation": 0.05, "decay": 10}),
    ("A1_decay20_t005", A1, {"truncation": 0.05, "decay": 20}),
    ("A1_top1k_t005", A1, {"truncation": 0.05, "decay": 10, "universe": "TOP1000"}),
]

BASE = {"neutralization": "SUBINDUSTRY", "decay": 10, "universe": "TOP3000",
        "truncation": 0.02}


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请重新登录")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/legs34_{stamp}.csv"
    fields = ["name", "alpha_id", "sharpe", "fitness", "turnover", "returns", "fails"]
    rows = []

    def flush():
        with open(out, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)

    for i, (name, expr, over) in enumerate(CONFIGS, 1):
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
            print(f'[{i}/{len(CONFIGS)}] {name:18s} {aid} S={row["sharpe"]} F={row["fitness"]} '
                  f'T={row["turnover"]} R={row["returns"]} FAIL={bad}', flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(CONFIGS)}] {name:18s} FAILED {str(e)[:130]}", flush=True)
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
              f'R={r["returns"]:<7} {r["name"]:18s} {r["alpha_id"]}  {r["fails"]}')
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
