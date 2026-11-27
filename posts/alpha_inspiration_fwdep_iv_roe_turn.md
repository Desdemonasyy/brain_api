# 【Alpha灵感】反转 + 前瞻 E/P + IV 溢价 + ROE：四步把 Fitness 从 1.38 做到 2.52

> 平台：BRAIN　Region：USA　Universe：TOP1000　Delay：1　Neutralization：MARKET
> 下文所有指标均为 **IS** 回测结果（IS Summary / PnL），不是 TEST。
> 每一步只动一个变量，方便对照。

目标 Alpha：**rK0pjmM1**　Sharpe 2.32 / Fitness 2.52 / Turnover 19.67% / Returns 23.17%

---

## 一、起点：反转 + 前瞻 E/P

反转单腿是池内最强的单信号（S1.97），但它只反映"短期被抛售"，没有价值锚。补一条分析师前瞻 E/P：用一致预期 EPS 除以收盘价，比已实现 E/P 领先一个财报周期。

```
-rank(ts_rank(returns, 5)) + rank(ts_rank(anl4_afv4_eps_mean / close, 126))
```

Settings：MARKET / decay 3 / TOP1000

| Alpha ID | Sharpe | Fitness | Turnover | Returns | 结果 |
|---|---|---|---|---|---|
| VkM1pp7w | 1.62 | 0.98 | 56.68% | 20.60% | FAIL：Fitness < 1 |

Sharpe 只有 1.62，换手 56.68%。收益其实不低（20.60%），问题在换手把 Fitness 压死了。

【截图位 1：VkM1pp7w 的 IS Summary + PnL】

---

## 二、加强一：加一条 IV 溢价腿

两条腿都在讲"别人怎么看这只票"，但维度不同：反转看价格被砸，IV 溢价看期权市场愿不愿意为上涨付钱。用 call 隐含波动 / Parkinson 已实现波动，比率有界，截面摊得开。

```
-rank(ts_rank(returns, 5)) + rank(ts_rank(anl4_afv4_eps_mean / close, 126)) + 0.5 * rank(ts_backfill(implied_volatility_call_120 / parkinson_volatility_120, 20))
```

Settings：MARKET / decay 3 / TOP1000

| Alpha ID | Sharpe | Fitness | Turnover | Returns |
|---|---|---|---|---|
| legpVvK5 | 2.03 | 1.38 | 53.13% | 24.59% |

Sharpe 1.62 → 2.03，Returns 24.59% 是当时全池最高。但换手还是 53%，Fitness 只有 1.38。

【截图位 2：legpVvK5 的 IS Summary + PnL】

这里先算清楚一件事：Fitness ≈ Sharpe × sqrt(Returns / max(Turnover, 12.5%))。换手 53% 时，根号里是 24.59/53.13 ≈ 0.46；如果换手能压到 12.5% 以内，分母锁死，同样收益下 Fitness 能翻一倍。所以后面所有动作都围绕"降换手，但不伤 Sharpe"。

---

## 三、弯路：想靠"先平滑再取分位"降换手，信号被抹掉

第一反应是把 5 日收益做 5 日均值，再取 60 日分位，只在相对位置变化时调仓；decay 从 3 提到 20。

```
rank(-ts_rank(ts_mean(returns, 5), 60)) + rank(ts_rank(anl4_afv4_eps_mean / close, 126))
```

| Alpha ID | Sharpe | Fitness | Turnover | Returns | 结果 |
|---|---|---|---|---|---|
| np6x8lAl（K1） | 0.86 | 0.82 | 12.54% | 11.43% | FAIL：Sharpe / Fitness 双低 |

换手确实进来了（12.54%），但 Sharpe 从 2.03 掉到 0.86。5 日反转的 alpha 就在"每天重排"这件事本身，破坏原始排序等于把信号删掉。

结论：降换手只能动 decay、truncation 这类"权重变化速度"的参数，不能动信号本身的横截面排序。

【截图位 3：np6x8lAl 的 IS Summary + PnL（作为反例）】

---

## 四、加强二：只动 decay，先找到 12.5% 那条线

同一个表达式，decay 3 → 10 / 20：

| Alpha ID | decay | Sharpe | Fitness | Turnover | Returns |
|---|---|---|---|---|---|
| akRj1wMx（L1） | 10 | 1.93 | 1.98 | 20.30% | 21.42% |
| QPWZGxZG（L2） | 20 | 1.76 | 2.18 | 11.86% | 19.14% |

L2 的 Sharpe 比 L1 低 0.17，但 Fitness 反超 0.20——因为换手第一次进到 12.5% 以内，分母锁定。这就是这条线最关键的定价：**多让 0.17 的 Sharpe，换 0.42 的换手，是划算的。**

【截图位 4：QPWZGxZG 的 IS Summary + PnL】

---

## 五、加强三：加第四条腿 ROE（rK0pjmM1）

前瞻 E/P 便宜可能是因为公司真的差。operating_income / equity 做质量过滤，把"便宜但烂"的名字压下去，权重给 0.5。

```
-rank(ts_rank(returns, 5)) + rank(ts_rank(anl4_afv4_eps_mean / close, 126)) + 0.5 * rank(ts_backfill(implied_volatility_call_120 / parkinson_volatility_120, 20)) + 0.5 * rank(ts_rank(operating_income / equity, 126))
```

**Settings：MARKET / decay 10 / TOP1000 / Delay 1**

| Alpha ID | Sharpe | Fitness | Turnover | Returns |
|---|---|---|---|---|
| **rK0pjmM1** | **2.32** | **2.52** | **19.67%** | **23.17%** |

对照同批次的其余变体：

| Alpha ID | 改动 | Sharpe | Fitness | Turnover |
|---|---|---|---|---|
| 2rG8lnn5 | 反转权重 1.5 | 2.07 | 1.88 | 28.16% |
| vRYwjLYa | 反转先取 3 日均值 | 1.95 | 2.04 | 20.25% |
| **rK0pjmM1** | **+0.5 ROE** | **2.32** | **2.52** | 19.67% |

ROE 这条腿把 Sharpe 从 1.93 推到 2.32，换手还从 20.30% 略降到 19.67%。质量腿对"便宜但烂"的过滤，同时也降低了高换手小票的权重。

【截图位 5：rK0pjmM1 的 IS Summary + PnL —— 用 IS 页，不要贴 TEST】

---

## 六、继续加强：把 ROE 权重和 decay 一起推

rK0pjmM1 的换手 19.67% 仍未锁定分母。继续两件事：ROE 权重 0.5 → 1.0，decay 10 → 15 / 20。

| Alpha ID | 改动 | Sharpe | Fitness | Turnover | Returns |
|---|---|---|---|---|---|
| np6xd78d | ROE 权重 1.0，decay 10 | 2.54 | 2.88 | 16.81% | 21.56% |
| 1YGk3Q8X | ROE 1.0，decay 15 | 2.45 | **3.12** | 12.52% | 20.29% |
| N1KxEgMw | ROE 1.0，decay 20 | 2.40 | 3.01 | 10.34% | 19.63% |

1YGk3Q8X 的换手 12.52%，刚好踩在 12.5% 边上，分母差一点没锁住；N1KxEgMw 把换手压到 10.34%，Fitness 3.01，Sharpe 只掉 0.05。到这里 Sharpe 2.40 ~ 2.45、Fitness 3.0 ~ 3.1，已经明显好过 rK0pjmM1。

【截图位 6：1YGk3Q8X 的 IS Summary + PnL】

---

## 七、走不通的两个方向（记录一下）

1. **纯期权微观结构单腿。** 用 option9 字段（pcr_oi / pcr_vol / breakeven / forward_price）做了 8 条单腿，最高 Sharpe 0.87（put/call 持仓比变化反向）。单腿撑不起 1.25 的门槛。
2. **社交媒体情绪波动。** -ts_std_dev(scl12_buzz, 20) 这类信号，最高 Sharpe 0.78。声量波动本身噪声太大，必须配价格或基本面才有方向。

这两批失败说明 rK0pjmM1 的分数不是"多试出来的"：单腿单独看都不成立，是四条腿的互补结构在起作用。

---

## 八、几条经验

1. **先看 Fitness 的公式再调参。** 换手在 12.5% 以上时，Fitness 的分母是换手本身，降换手等于直接提 Fitness；低于 12.5% 之后，再降换手没有任何收益。
2. **降换手不要碰信号的排序。** 动 decay、truncation 可以，动 ts_rank 的窗口或先做均值平滑，会把 alpha 直接抹掉（K1 的 Sharpe 从 2.03 掉到 0.86）。
3. **一次只改一个变量。** rK0pjmM1 的 0.39 Sharpe 增量能明确归因到 ROE 腿，而不是某个权重魔法数字。
4. **质量腿同时降换手。** 加 ROE 后 Sharpe 上升、换手下降，这种"两头都赚"的腿值得优先试。
5. **反转腿的窗口别贪。** 5 日反转是最强的，但也是最贵的；要降成本去动 decay，不要动窗口。

---

*个人研究记录，不构成投资建议。全部指标为 BRAIN 平台 IS 回测结果。*
