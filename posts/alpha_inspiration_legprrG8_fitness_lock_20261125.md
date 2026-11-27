# 【Alpha灵感】把"换手锁定线"当目标函数：legprrG8 四腿合成，IS Sharpe 2.24 / Fitness 2.60

> 全部为 IS（In-Sample）结果。Settings 除注明外统一：Region = USA，Universe = TOP1000，Delay = 1，Neutralization = MARKET。
> Fitness 公式：`F = Sharpe × sqrt(|Returns| / max(Turnover, 12.5%))`。这个公式是后面所有决策的依据。

---

## 一、起点：一条 Sharpe 2.11 却交不掉的信号

最初的想法很直接——看涨与看跌隐含波动率的价差，代表期权市场对方向的"付费意愿"。

```
rank(ts_backfill(implied_volatility_call_120 - implied_volatility_put_120, 20))
```

| Alpha ID | Sharpe | Fitness | Turnover | Returns | 结果 |
|---|---|---|---|---|---|
| 78YpYw6b | 2.11 | 1.21 | 26.88% | 8.80% | FAIL：权重过度集中；子池 Sharpe 0.69 < 0.91 |

Sharpe 够，但权重集中、换手 26.88%。问题出在"价差"是绝对量：期权链厚的少数名字数值大，rank 之后权重全堆在头部。先解决分布问题。

> 【截图位 1：78YpYw6b 的 IS Summary】

---

## 二、想法一：价差 → 溢价比率

把绝对价差换成"call 隐含波动 / 已实现波动（Parkinson）"的比率，截面分布天然均匀，权重自动摊开。

```
rank(ts_backfill(implied_volatility_call_120 / parkinson_volatility_120, 20))
```

| Alpha ID | Sharpe | Fitness | Turnover | Returns |
|---|---|---|---|---|
| rK7xGmAE | 1.60 | 1.32 | 6.56% | 8.45% |

换手 26.88% → 6.56%，Fitness 反而从 1.21 升到 1.32。经济含义：call 隐含波动相对实际波动越贵，说明市场为"上涨"支付的溢价越高，这是情绪/拥挤度，不是价格动量。

> 【截图位 2：rK7xGmAE 的 IS Summary】

---

## 三、想法二：补一条估值腿（EBIT / 市值）

单腿 1.60 不够。情绪腿的问题是会在情绪反转时整体回撤，需要一条基本面折价腿对冲。选 EBIT 而不是净利润，是为了避开税率和一次性损益的噪声。

```
rank(ts_rank(anl4_ebit_value / cap, 126)) + rank(ts_backfill(implied_volatility_call_120 / parkinson_volatility_120, 20))
```

| Alpha ID | Sharpe | Fitness | Turnover | Returns |
|---|---|---|---|---|
| aka5XGj2 | 1.87 | 1.90 | 7.68% | 12.86% |

Fitness 1.32 → 1.90，换手只多了 1.1 个百分点。低换手的正交腿几乎是"免费"的增量。

> 【截图位 3：aka5XGj2 的 IS Summary】

---

## 四、想法三：再加一条质量腿（ROE）

估值便宜有时是因为公司真的差。用 `operating_income / equity` 做质量过滤，把"便宜但烂"的名字排到后面。

```
rank(ts_rank(anl4_ebit_value / cap, 126)) + rank(ts_backfill(implied_volatility_call_120 / parkinson_volatility_120, 20)) + 0.5 * rank(ts_rank(operating_income / equity, 126))
```

| Alpha ID | Sharpe | Fitness | Turnover | Returns |
|---|---|---|---|---|
| E5Q903PL | 2.02 | 2.05 | 7.82% | 12.92% |

三腿、换手 7.82%、Sharpe 破 2、Fitness 破 2。结构变成"估值 + 情绪 + 质量"，三条腿的驱动互不重叠。

> 【截图位 4：E5Q903PL 的 IS Summary】

---

## 五、想法四：中性化和 decay 是放大器，不是新信号

同一表达式，只改 Settings（SUBINDUSTRY + decay 3）：

| Alpha ID | 中性化 / decay | Sharpe | Fitness | Turnover | Returns |
|---|---|---|---|---|---|
| 9qGZbZ2o | SUBINDUSTRY / 3 | 2.29 | 2.22 | 15.41% | 14.52% |

Sharpe 和收益都上去了，但换手从 7.82% 翻到 15.41%。记住这条：**中性化能提 Sharpe，但会把换手一起推高**，而换手一旦超过 12.5%，就会直接进 Fitness 的分母。

> 【截图位 5：9qGZbZ2o 的 IS Summary】

---

## 六、想法五：相关性只能靠"两个差异源"破

9qGZbZ2o 提交后，同表达式的 MARKET 版本自相关 0.7743 被拒；再加"换腿"后 0.7303，仍被拒。实测经验值：

- 单换中性化：相关性约降 0.04 ~ 0.18
- 单换 Universe：降幅更小

结论：想稳定压到 0.7 以下，必须**中性化 + 换腿**同时改，单点微调没有意义。

---

## 七、想法六：ROE → 资产周转率，先把相关性拆开

`sales / assets` 与 ROE 同属"经营效率"，但一个是利润率、一个是周转，截面排序差异大，是天然的换腿对象。

```
rank(ts_rank(anl4_ebit_value / cap, 126)) + rank(ts_backfill(implied_volatility_call_120 / parkinson_volatility_120, 20)) + 1.0 * rank(ts_rank(sales / assets, 126))
```

| Alpha ID | Sharpe | Fitness | Turnover | Returns |
|---|---|---|---|---|
| LL8VXjd6 | 1.92 | 2.21 | 13.51% | 17.87% |
| j2VzwkrE | 1.80 | 2.00 | 12.06% | 15.41% |

换腿确实压住了相关性（j2VzwkrE 已在当日提交），但 EBIT 和周转率都带周期属性，Sharpe 回落到 1.8 附近。Fitness 还在 2 以上，说明单位换手赚的钱变多了。

> 【截图位 6：j2VzwkrE 的 IS Summary】

---

## 八、想法七（最终版）：估值腿换成分析师前瞻 E/P

EBIT 是已实现的会计数字，前瞻 E/P 用的是分析师一致预期 EPS，时间上领先一个财报周期，且与 EBIT/cap 的截面排序差异足够大。同时把 ROE 权重提到 1.5 让质量主导，周转率保持 1.0 稀释行业暴露。

```
rank(ts_rank(anl4_afv4_eps_mean / close, 126)) + rank(ts_backfill(implied_volatility_call_120 / parkinson_volatility_120, 20)) + 1.5 * rank(ts_rank(operating_income / equity, 126)) + 1.0 * rank(ts_rank(sales / assets, 126))
```

**Settings：Neutralization = MARKET，Decay = 3，Universe = TOP1000，Delay = 1**

| Alpha ID | Sharpe | Fitness | Turnover | Returns |
|---|---|---|---|---|
| **legprrG8（FwdEP_IV_ROE15_Turn_Mkt）** | **2.24** | **2.60** | **10.88%** | **16.84%** |

同结构、只换估值口径的对照：

| Alpha ID | 估值腿 | Sharpe | Fitness | Turnover | Returns |
|---|---|---|---|---|---|
| xAlOevzW | EBIT / cap | 1.83 | 1.93 | 9.48% | 13.88% |
| vRYwdx73 | CF / cap | 2.07 | 2.28 | 11.00% | 15.18% |
| **legprrG8** | **前瞻 E/P** | **2.24** | **2.60** | 10.88% | 16.84% |

同样的三条辅助腿，只换估值口径，Sharpe 1.83 → 2.24、Fitness 1.93 → 2.60，换手还略降。这 0.4 的 Sharpe 全部来自"预期差"这一条腿，不是参数拟合。

关键在换手：10.88% < 12.5%，Fitness 的分母被锁定，同样的 Sharpe 能换来更高的 F。这是这条 Alpha 值钱的另一半原因。

> 【截图位 7：legprrG8 的 IS Summary 与 PnL —— 必须是 IS 页，不是 TEST】

---

## 九、继续加强：用 5 日反转腿再抬一档 Fitness

四腿里质量腿权重偏高会让组合偏"慢"。加一条短周期反转，一是补足短周期 alpha，二是把换手从 10.88% 提到 12.5% 附近但不超过锁定线太多——因为 T < 12.5% 之后，压换手已经不能再提 F，只能靠提 Sharpe。

```
-rank(ts_rank(returns, 5)) + rank(ts_rank(anl4_afv4_eps_mean / close, 126)) + 0.5 * rank(ts_backfill(implied_volatility_call_120 / parkinson_volatility_120, 20)) + 1.0 * rank(ts_rank(operating_income / equity, 126))
```

**Settings：MARKET，Decay = 15，TOP1000**

| Alpha ID | Sharpe | Fitness | Turnover | Returns |
|---|---|---|---|---|
| 1YGk3Q8X | 2.45 | **3.12** | 12.52% | 20.29% |
| N1KxEgMw（decay 20） | 2.40 | 3.01 | 10.34% | 19.63% |

收益从 16.84% 抬到 20.29%，Sharpe 2.24 → 2.45，Fitness 破 3。这条是同一思路在新一代结构下的延续，和 legprrG8 的差异已经足够大，可以作为独立 Alpha 使用。

> 【截图位 8：1YGk3Q8X 的 IS Summary】

---

## 十、四腿分工

| 腿 | 表达式 | 经济含义 | 作用 |
|---|---|---|---|
| 估值 | `ts_rank(anl4_afv4_eps_mean / close, 126)` | 分析师前瞻 E/P，预期差 | 主 alpha 来源 |
| 情绪 | `implied_volatility_call_120 / parkinson_volatility_120` | call 隐含波动相对已实现波动的溢价 | 低换手、低相关的正交源 |
| 质量 | `ts_rank(operating_income / equity, 126)` × 1.5 | 盈利能力，剔除"便宜但烂" | 降回撤、提 Fitness |
| 效率 | `ts_rank(sales / assets, 126)` × 1.0 | 资产周转，稀释行业与周期暴露 | 降行业暴露、稳子池 |

---

## 十一、复盘

1. **先看权重分布，再看 Sharpe。** 价差类信号 Sharpe 2.11 但过不了集中度检查，换成比率就解决了。
2. **换手是设计出来的。** 全程 126 天 ts_rank + decay 3，换手稳定在 7%~11%，没有一次靠调 decay 硬压。
3. **Fitness 有拐点。** `T < 12.5%` 之后分母锁定，继续压换手是在浪费 alpha，此时唯一有效的动作是提 Sharpe 或提收益。
4. **相关性只能靠两个差异源破。** 单换中性化约降 0.04，必须再叠加换腿。
5. **一次只改一条腿。** 最终版能明确说清 0.4 的 Sharpe 来自前瞻 E/P，而不是某个权重魔法数字。
6. **别让组合长得像教科书。** 四腿里只有 ROE 是常规风格因子，其余三条都是数据口径上的差异化选择，这决定了自相关能不能过。

---

*个人研究记录与复现过程，不构成投资建议。所有指标均为 BRAIN 平台 IS 回测结果。*
