"""第四批：news18 情绪向量 + pv13 关系网络结构（两个从未使用过的数据集）。

news18：VECTOR 字段需 vec_avg 聚合；rp_* 是 MATRIX 日频字段（历史实测换手 120-133%，弃用）。
pv13：产业链/竞争关系图谱的静态结构指标，换手极低，但需防 LOW_TURNOVER。
"""
import csv
import time
from datetime import datetime

import brain

SIGNALS = [
    # news18 VECTOR 情绪：波动维度（与 A6 的均值维度是不同信号类型）
    ("n18_ssc_std", "-ts_std_dev(vec_avg(nws18_ssc), 20)",
     {"neutralization": "SUBINDUSTRY", "decay": 20}),
    ("n18_qcm_std", "-ts_std_dev(vec_avg(nws18_qcm), 20)",
     {"neutralization": "SUBINDUSTRY", "decay": 20}),
    # news18 VECTOR 情绪：均值维度
    ("n18_nip_mean", "group_rank(ts_mean(vec_avg(nws18_nip), 20), subindustry)",
     {"neutralization": "MARKET", "decay": 20}),
    ("n18_lna_mean", "group_rank(ts_mean(vec_avg(nws18_ghc_lna), 20), subindustry)",
     {"neutralization": "MARKET", "decay": 20}),
    # pv13 网络结构：竞争者密度（反向）与客户质量
    ("pv13_comp_pr", "group_rank(pv13_com_page_rank, sector)",
     {"neutralization": "MARKET", "decay": 4}),
    ("pv13_cust_pr", "group_rank(pv13_ustomergraphrank_page_rank, sector)",
     {"neutralization": "MARKET", "decay": 4}),
    ("pv13_comp_auth", "group_rank(pv13_com_rk_au, sector)",
     {"neutralization": "MARKET", "decay": 4}),
    ("pv13_sector_n", "group_rank(pv13_revere_key_sector_total, sector)",
     {"neutralization": "MARKET", "decay": 4}),
]


def main():
    s = brain.load()
    if not brain.authenticated(s):
        print("cookie 失效")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"results/newsrc4_{stamp}.csv"
    fields = ["name", "alpha_id", "sharpe", "fitness", "turnover", "returns", "fails"]
    rows = []

    def flush():
        with open(out, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)

    for i, (name, expr, over) in enumerate(SIGNALS, 1):
        try:
            sim_id, retry_after = brain.simulate(s, expr, **over)
            time.sleep(retry_after)
            d = brain.wait(s, sim_id)
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
            print(f'[{i}/{len(SIGNALS)}] {name:14s} {aid}  S={row["sharpe"]}  '
                  f'F={row["fitness"]}  T={row["turnover"]}  R={row["returns"]}  '
                  f'FAIL={bad}', flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(SIGNALS)}] {name:14s} FAILED: {str(e)[:200]}", flush=True)
            rows.append({"name": name, "alpha_id": "", "sharpe": "", "fitness": "",
                         "turnover": "", "returns": "", "fails": "ERROR"})
        flush()
        time.sleep(2)

    ok = [r for r in rows if isinstance(r["sharpe"], (int, float))]
    ok.sort(key=lambda r: abs(r["sharpe"]), reverse=True)
    print("\n=== 按 |Sharpe| 排序 ===")
    for r in ok:
        print(f'{r["sharpe"]:6.2f}  F={r["fitness"]:<5} T={r["turnover"]:<7} {r["name"]:14s} '
              f'{r["alpha_id"]}  {r["fails"]}')
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
