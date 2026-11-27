"""第三十五阶段：Alpha158 纯价格因子验证（全新数据源，与 fundamental6 正交）。

之前弱腿失败的数学根因：
- 全来自 fundamental6 会计比率，腿间 IC 相关性太高
- 会计数据季度更新 → T~5%，Returns 天然受限 ~3-5%
- IC >= 0.99 的冗余因子（capex vs 应计 vs 应收）组合只剩噪声

Alpha158 因子设计原则：
- 纯价格/成交量（pv1），与 fundamental6 正交
- 用 BRAIN Fast Expression 确实支持的算子
- 先单腿拿基线，再组合（这次腿间低相关是硬约束）

Alpha158 类别 → BRAIN 映射：
- RESI（回归残差）= ts_regression(close, 1, 20, rettype=2) / close ?
- RSQR（拟合优度）= ts_regression(close, 1, 20, rettype=3) ?
- IdxMax/IdxMin   → ts_arg_max / ts_arg_min (需验证)
- Corr(close, log(vol+1), N) = ts_corr(close, log(volume+1), N)
- Rank(close, N)  = ts_rank(close, N)
- Std(volume, N)  = ts_std_dev(volume, N)

重点关注这几类（BRAIN 支持 + 未测过）：
1. 极值位置类：20日内最高/最低价出现在第几天
2. 价量相关类：价格涨跌与成交量变化是否同步
3. 收益分布类：正收益天数 vs 负收益天数
4. 波动结构类：std(volume, N)/volume
"""
import csv
import time
from datetime import datetime

import brain

BASE = {"neutralization": "SUBINDUSTRY", "decay": 10, "universe": "TOP3000",
        "truncation": 0.02}

# ------ 纯价格/成交量因子（pv1 数据源）------
# 趋势类
ROC5 = "ts_rank(close / lag(close, 5), 60)"          # 5 日动量（时间序列分位）
ROC20 = "ts_rank(close / lag(close, 20), 60)"        # 20 日动量

# 极值位置类（IdxMax/IdxMin → ts_arg_max/min，需验证）
# BRAIN 里有 ts_arg_max(high, 20) 返回最大值的位置索引（0-1 归一化？）
# 先试，ERROR 就说明算子名不对
IMAX20 = "group_rank(ts_arg_max(high, 20), subindustry)"
IMIN20 = "group_rank(ts_arg_min(low, 20), subindustry)"

# 价量相关类
CORR20 = "group_rank(ts_corr(close, log(volume + 1), 20), subindustry)"
CORR60 = "group_rank(ts_corr(close, log(volume + 1), 60), subindustry)"

# 收益分布类：正收益天数比例 - 负收益天数比例
# 用 ts_sum(sign(returns), N) 但 BRAIN 没有 sign... 
# 用 conditional +1/-1：mean(close > lag(close,1), 20) - mean(close < lag(close,1), 20)
SUMD20 = "group_rank(ts_mean(close > lag(close, 1), 20) - ts_mean(close < lag(close, 1), 20), subindustry)"
CNTD20 = SUMD20  # 同义

# 波动结构类
STD_VOL20 = "group_rank(ts_std_dev(volume, 20) / ts_mean(volume, 20), subindustry)"

# 相对强弱（RSV）
RSV20 = "group_rank((close - ts_min(low, 20)) / (ts_max(high, 20) - ts_min(low, 20) + 0.001), subindustry)"

# ------ 单腿基线 ------
SINGLE = [
    ("ROC5_mom", f"rank({ROC5})", {"decay": 10}),
    ("ROC20_mom", f"rank({ROC20})", {"decay": 10}),
    ("IMAX20_pos", f"rank({IMAX20})", {"decay": 10}),
    ("IMIN20_pos", f"rank(-{IMIN20})", {"decay": 10}),
    ("CORR20_vol", f"rank(-{CORR20})", {"decay": 10}),  # 价量负相关 = 放量跌 = 反转
    ("CORR60_vol", f"rank(-{CORR60})", {"decay": 10}),
    ("SUMD20_dist", f"rank(-{SUMD20})", {"decay": 10}),  # 收益天数差低 = 近期阴跌
    ("STD_VOL20", f"rank(-{STD_VOL20})", {"decay": 10}),  # 成交量波动低 = 低流动性
    ("RSV20_strength", f"rank(-{RSV20})", {"decay": 10}),  # 相对位置低 = 超卖
]

# ------ 跨数据源弱腿组合（关键！之前没试过的数据源交叉组合）------
# 组合原则：每条腿来自不同数据源/类别，确保低 IC 相关
# 数据源分类：
# A = pv1 价格动量（ROC5）
# B = pv1 极值位置（IMAX20）
# C = pv1 价量相关（CORR20）
# D = pv1 收益分布（SUMD20）
# E = fundamental6 存货（INV）—— 唯一保留的会计弱腿，验证"价格+会计"是否真正交

INV = "ts_rank(inventory / assets, 126)"

CROSS = [
    # 纯价格内部组合（数据源相同但类别不同）
    ("X1_cross_price", f"rank(-{ROC5}) + rank(-{IMAX20})", {"decay": 10}),
    ("X2_cross_price", f"rank(-{CORR20}) + rank(-{SUMD20})", {"decay": 10}),
    ("X3_cross_price", f"rank(-{ROC5}) + rank(-{CORR20}) + rank(-{SUMD20})", {"decay": 10}),
    # 跨数据源（pv1 + fundamental6）
    ("X4_price_acc", f"rank(-{ROC5}) - rank({INV})", {"decay": 10}),
    ("X5_price_acc", f"rank(-{CORR20}) - rank({INV})", {"decay": 10}),
    # 纯价格 4 腿（最分散）
    ("X6_all_price", f"rank(-{ROC5}) + rank(-{IMAX20}) + rank(-{CORR20}) + rank(-{SUMD20})", {"decay": 10}),
]

LEGS = SINGLE + CROSS


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效，请重新登录")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/legs35_{stamp}.csv"
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
            print(f'[{i}/{len(LEGS)}] {name:18s} {aid} S={row["sharpe"]} F={row["fitness"]} '
                  f'T={row["turnover"]} R={row["returns"]} FAIL={bad}', flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(LEGS)}] {name:18s} FAILED {str(e)[:130]}", flush=True)
            rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                         "turnover": "", "returns": "", "fails": "ERROR"})
        flush()
        time.sleep(2)

    ok = [r for r in rows
          if isinstance(r["sharpe"], (int, float)) and isinstance(r["fitness"], (int, float))]
    ok.sort(key=lambda r: r["sharpe"], reverse=True)
    print("\n=== 按 Sharpe 排序（会计弱腿基准：capex0.46 存货0.77）===")
    print("=== 纯价格因子首次测试，Sharpe >= 1.0 即算突破 ===")
    for r in ok:
        print(f'{r["sharpe"]:6.2f}  F={r["fitness"]:<5} T={r["turnover"]:<7} '
              f'R={r["returns"]:<7} {r["name"]:18s} {r["alpha_id"]}  {r["fails"]}')
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
