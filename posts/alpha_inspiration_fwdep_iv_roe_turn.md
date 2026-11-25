# 【Alpha灵感】从 IV 价差到四腿合成：Sharpe 1.60 → 2.24 的七步复现记录

> 平台：BRAIN　Region：USA　Universe：TOP1000　Delay：1
> 下文所有指标均为 **IS** 回测结果（IS Summary / PnL），不是 TEST。
> 每一步只动一个变量，方便对照。

---

## 一、起点：一条 Sharpe 2.11 但过不了检查的信号

最早从期权数据入手，看涨-看跌隐含波动率价差，是最直观的情绪代理：call 端 IV 比 put 端贵，说明市场愿意为上涨付溢价。

```
rank(ts_backfill(implied_volatility_call_120 - implied_volatility_put_120, 20))
```

| Alpha ID | Sharpe | Fitness | Turnover | Returns | 结果 |
|---|---|---|---|---|---|
| 78YpYw6b | 2.11 | 1.21 | 26.88% | 8.80% | FAIL：权重过度集中；子池 Sharpe 0.69 < 0.91 |

Sharpe 是有，但权重压在少数期权链厚的名字上，换手也偏高。问题出在"价差"这个口径本身：绝对量在截面上分布很偏。

【截图位 1：78YpYw6b 的 IS Summary + PnL】

---

## 二、第一次改造：把价差换成比率

同样的经济含义，改成"隐含波动 / 已实现波动"的比率。比率天然有界，截面摊得更开。

```
rank(ts_backfill(implied_volatility_call_120 / parkinson_volatility_120, 20))
```

| Alpha ID | Sharpe | Fitness | Turnover | Returns |
|---|---|---|---|---|
| rK7xGmAE | 1.60 | 1.32 | 6.56% | 8.45% |

换手 26.88% → 6.56%，Fitness 从 1.21 升到 1.32。代价是 Sharpe 掉了 0.5，但权重集中问题直接解决。这一步确认了：单腿只能到 1.6 附近，得找正交的腿。

【截图位 2：rK7xGmAE 的 IS Summary + PnL】

---

## 三、加强一：配一条估值腿 EBIT / 市值

波动率溢价是"情绪"，缺一条"基本面折价"来对冲情绪反转。这里用 EBIT 而不是净利润，少受税率和一次性损益干扰。

```
rank(ts_rank(anl4_ebit_value / cap, 126)) + rank(ts_backfill(implied_volatility_call_120 / parkinson_volatility_120, 20))
```

| Alpha ID | Sharpe | Fitness | Turnover | Returns |
|---|---|---|---|---|
| aka5XGj2 | 1.87 | 1.90 | 7.68% | 12.86% |

两条腿相关性低，Fitness 从 1.32 跳到 1.90，换手只多了 1.1 个百分点。低换手的正交腿是"免费"的。

【截图位 3：aka5XGj2 的 IS Summary + PnL】

---

## 四、加强二：加第三条腿 ROE

估值便宜可能是因为公司真的差。用 operating_income / equity 做质量过滤，把"便宜但烂"的名字压下去。

```
rank(ts_rank(anl4_ebit_value / cap, 126)) + rank(ts_backfill(implied_volatility_call_120 / parkinson_volatility_120, 20)) + 0.5 * rank(ts_rank(operating_income / equity, 126))
```

| Alpha ID | Sharpe | Fitness | Turnover | Returns |
|---|---|---|---|---|
| E5Q903PL | 2.02 | 2.05 | 7.82% | 12.92% |

三腿、换手 7.82%、Sharpe 和 Fitness 双破 2。结构变成"估值 + 情绪 + 质量"，三条腿的经济逻辑互不重叠。

【截图位 4：E5Q903PL 的 IS Summary + PnL】

顺带记录一个分歧点：同表达式换成 SUBINDUSTRY + decay 3，Sharpe 能到 2.29（9qGZbZ2o，T15.41%），但换手翻倍、自相关也一起上来。中性化是放大器，不是新信号。

---

## 五、加强三：ROE 换资产周转率，权重给满

ROE 和 sales/assets 同属经营效率，但驱动不同：一个看利润率，一个看周转。截面上排序差异足够大，可以拿来降行业暴露。

```
rank(ts_rank(anl4_ebit_value / cap, 126)) + rank(ts_backfill(implied_volatility_call_120 / parkinson_volatility_120, 20)) + 1.0 * rank(ts_rank(sales / assets, 126))
```

| Alpha ID | Sharpe | Fitness | Turnover | Returns |
|---|---|---|---|---|
| LL8VXjd6 | 1.92 | 2.21 | 13.51% | 17.87% |
| j2VzwkrE（最终权重版） | 1.80 | 2.00 | 12.06% | 15.41% |

Sharpe 回落到 1.8 附近，因为 EBIT 和周转率都带周期属性；但 Fitness 还在 2 以上，单位换手赚的钱变多了。

【截图位 5：j2VzwkrE 的 IS Summary + PnL】

---

## 六、加强四（最终版）：估值腿换成分析师前瞻 E/P

EBIT 是已实现的会计数，前瞻 E/P 用分析师一致预期 EPS，时间上领先一个财报周期。同时 ROE 权重给到 1.5 让质量重新主导，周转率保持 1.0 稀释行业暴露。

```
rank(ts_rank(anl4_afv4_eps_mean / close, 126)) + rank(ts_backfill(implied_volatility_call_120 / parkinson_volatility_120, 20)) + 1.5 * rank(ts_rank(operating_income / equity, 126)) + 1.0 * rank(ts_rank(sales / assets, 126))
```

**Settings：Neutralization = MARKET，Decay = 3，Universe = TOP1000，Delay = 1**

| Alpha ID | Sharpe | Fitness | Turnover | Returns |
|---|---|---|---|---|
| legprrG8 | **2.24** | **2.60** | **10.88%** | **16.84%** |

对照实验：同样三条辅助腿，只换估值口径。

| Alpha ID | 估值腿 | Sharpe | Fitness | Turnover | Returns |
|---|---|---|---|---|---|
| xAlOevzW | EBIT / cap | 1.83 | 1.93 | 9.48% | 13.88% |
| vRYwdx73 | CF / cap | 2.07 | 2.28 | 11.00% | 15.18% |
| legprrG8 | 前瞻 E/P | 2.24 | 2.60 | 10.88% | 16.84% |

三条辅助腿完全不动，只换估值腿：Sharpe 1.83 → 2.24，Fitness 1.93 → 2.60，换手还略降。这 0.4 的 Sharpe 来自"预期差"这条腿，不是参数拟合。

【截图位 6：legprrG8 的 IS Summary + PnL —— 用 IS 页，不要贴 TEST】

---

## 七、四腿分工

| 腿 | 表达式 | 经济含义 | 作用 |
|---|---|---|---|
| 估值 | ts_rank(anl4_afv4_eps_mean / close, 126) | 分析师前瞻 E/P | 主 alpha 来源 |
| 情绪 | implied_volatility_call_120 / parkinson_volatility_120 | call IV 相对已实现波动的溢价 | 低换手、低相关的正交源 |
| 质量 | ts_rank(operating_income / equity, 126) × 1.5 | 盈利能力，剔除"便宜但烂" | 降回撤、提 Fitness |
| 效率 | ts_rank(sales / assets, 126) × 1.0 | 资产周转 | 稀释行业与周期暴露 |

---

## 八、几条经验

1. 价差类信号先看权重集中度。绝对量价差 Sharpe 2.11 也过不了检查，改比率就解决。
2. 换手是设计出来的，不是调出来的。全程 ts_rank 126 天 + decay 3，换手稳定 7%~11%；想靠 decay 硬压换手，Sharpe 会一起掉。
3. 相关性只能靠两个差异源破。实测换中性化只降约 0.04，得再叠换腿或换 Universe。
4. 一次只改一条腿。最终版能说清楚 0.4 的 Sharpe 来自前瞻 E/P，而不是某个权重魔法数字。
5. 越像多因子教科书模板的组合越容易撞车。这四腿里只有 ROE 是常规风格因子，其余三条都是数据口径上的差异化选择。

---

*个人研究记录，不构成投资建议。全部指标为 BRAIN 平台 IS 回测结果。*
