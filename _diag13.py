"""用单字段查询快速验证 analyst4 候选字段是否存在。"""
import time

import brain

s = brain.load()
if not brain.authenticated(s):
    print("cookie 失效，请重新登录")
    raise SystemExit(1)

BASE = "https://api.worldquantbrain.com"
CAND = [
    "anl4_target_price", "anl4_tp_mean", "anl4_afv4_target_price",
    "anl4_targetprice", "anl4_tp", "anl4_price_target",
    "anl4_rating_mean", "anl4_rating", "anl4_afv4_rating",
    "anl4_recommendation", "anl4_rec_mean", "anl4_rating_change",
    "anl4_lt_growth", "anl4_sales_mean", "anl4_net_income_mean",
    "anl4_ebitda_mean", "anl4_fcf_mean", "anl4_dps_mean",
]

for fid in CAND:
    try:
        r = s.get(f"{BASE}/data-fields/{fid}",
                  headers={"Accept": "application/json;version=2.0"}, timeout=45)
        if r.status_code == 200:
            d = r.json()
            print(f'OK   {fid:<28} {d.get("type",""):<7} cov={d.get("coverage")} '
                  f'users={d.get("alphaCount")}  {(d.get("description") or "")[:44]}', flush=True)
        else:
            print(f'{r.status_code:<4} {fid}', flush=True)
    except Exception as e:  # noqa: BLE001
        print(f'EXC  {fid} {str(e)[:60]}', flush=True)
    time.sleep(1.5)
