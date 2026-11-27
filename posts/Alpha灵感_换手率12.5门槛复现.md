# 【Alpha灵感】换手率 12.5% 这道隐形门槛：一条多腿 Alpha 的复现与三级加强记录

先给结论：同一条信号，Sharpe 只从 2.03 涨到 2.42（+19%），Fitness 却从 1.38 涨到 3.15（+128%）。差别不在信号强度，而在换手率。BRAIN 的 Fitness 公式是：

```
Fitness = Sharpe × sqrt(|Returns| / max(Turnover, 0.125))
```

分母在 12.5% 处有地板。换手高于它时，每降一点换手都在直接买 Fitness；换手低于它时，再降换手没有任何奖励，只会白丢收益。下面是把一条"反转 + 价值 + 期权"多腿 Alpha 从 53% 换手压到 9.5% 的完整过程，每一档附一行复现代码和 IS 结果。

---

## 一、原始想法：短期反转 + 前瞻 E/P + 看涨 IV 溢价

三条腿的经济逻辑：

- 5 日反转：短期超跌反弹；
- 前瞻 E/P（分析师 4 季度 EPS 均值 / 收盘价）：估值便宜；
- 看涨 IV / Parkinson 已实现波动率：期权市场给出的上行对冲溢价偏高。

复现代码（Region USA，Universe TOP1000，Neutralization MARKET，Decay 3）：

```text
-rank(ts_rank(returns, 5))
+ rank(ts_rank(anl4_afv4_eps_mean / close, 126))
+ 0.5 * rank(ts_backfill(implied_volatility_call_120 / parkinson_volatility_120, 20))
```

IS 结果：**Sharpe 2.03 / Fitness 1.38 / Turnover 53.13% / Returns 24.59%**

【IS 回测图 1：J2（legpVvK5），S2.03 / F1.38 / T53.13%】

问题很明确：24.59% 的收益在这个池子里已经很高，但 53% 的换手把 Fitness 压到 1.38，离 1.0 的提交线只差一点运气。

---

## 二、加强一：补质量腿（ROE），先把信号做厚

纯反转 + 估值，多空两侧都容易踩到"便宜但快烂掉"的公司。加一条 ROE 质量腿，等于要求"便宜但不烂"，同时把 decay 从 3 提到 10：

```text
-rank(ts_rank(returns, 5))
+ rank(ts_rank(anl4_afv4_eps_mean / close, 126))
+ 0.5 * rank(ts_backfill(implied_volatility_call_120 / parkinson_volatility_120, 20))
+ 0.5 * rank(ts_rank(operating_income / equity, 126))
```

IS 结果：**Sharpe 2.32 / Fitness 2.52 / Turnover 19.67% / Returns 23.17%**

【IS 回测图 2：L4（rK0pjmM1），S2.32 / F2.52 / T19.67%】

Sharpe +0.29，换手从 53% 砍到 19.67%，Fitness 接近翻倍。注意这里换手下降主要来自 decay 3→10，不是信号本身变慢。

---

## 三、加强二：质量腿权重翻倍（0.5 → 1.0）

只动 ROE 权重，其余参数不变：

```text
-rank(ts_rank(returns, 5))
+ rank(ts_rank(anl4_afv4_eps_mean / close, 126))
+ 0.5 * rank(ts_backfill(implied_volatility_call_120 / parkinson_volatility_120, 20))
+ 1.0 * rank(ts_rank(operating_income / equity, 126))
```

IS 结果：**Sharpe 2.54 / Fitness 2.88 / Turnover 16.81% / Returns 21.56%**

【IS 回测图 3：M3（np6xd78d），S2.54 / F2.88 / T16.81%】

Sharpe 再 +0.22，收益略降（23.17% → 21.56%），换手再降 2.9 个点。Fitness 2.88，离 3.0 一步之遥。

---

## 四、加强三（N 轮）：只动 decay，把换手打穿 12.5%

关键一步。M3 的换手 16.81% 还在 12.5% 之上，分母未锁定。三条 decay 对照，其余参数完全不动：

| 变体 | Decay | Sharpe | Fitness | Turnover | Returns |
|---|---|---|---|---|---|
| N1（1YGk3Q8X） | 15 | 2.45 | 3.12 | 12.52% | 20.29% |
| N2（N1KxEgMw） | 20 | 2.40 | 3.01 | 10.34% | 19.63% |
| N3（gJrkNZj0） | 25 | 2.37 | 2.94 | 9.03% | 19.18% |

【IS 回测图 4：N1（1YGk3Q8X），S2.45 / F3.12 / T12.52%】

decay 15 这一档换手 12.52%，只越过锁定线 0.02 个百分点，F 仍按未锁定算，反而拿到本批最高 Fitness；decay 20 退到 10.34%，分母锁死，F 稳在 3.0 以上。这 0.02 个点就是"擦线"和"安全边际"的区别，真要提交建议留足缓冲。

顺手排掉一个无效动作：truncation 0.05 在 decay 15 / decay 20 两档上，S/F/T/R 四项完全一模一样，线性 rank 复合下截断没有触发任何持仓变化，这一项可以省掉。

---

## 五、最后一档：IV 腿权重 0.5 → 1.0 + 保持 decay 20

```text
-rank(ts_rank(returns, 5))
+ rank(ts_rank(anl4_afv4_eps_mean / close, 126))
+ 1.0 * rank(ts_backfill(implied_volatility_call_120 / parkinson_volatility_120, 20))
+ 1.0 * rank(ts_rank(operating_income / equity, 126))
```

IS 结果：**Sharpe 2.42 / Fitness 3.15 / Turnover 9.52% / Returns 21.20%**

【IS 回测图 5：N7（2rG8gpKx），S2.42 / F3.15 / T9.52% / R21.20%】

对比 decay 20 的 IV 0.5 版（N2）：Sharpe 2.40→2.42，收益 19.63%→21.20%，换手 10.34%→9.52%，Fitness 3.01→3.15。期权 IV 溢价与 ROE 质量两条腿不同源，加权不伤换手，是这一轮唯一"白赚"的一步。

同一批里还有两条反向验证：

- ROE 权重继续加到 1.5（N6，XgNm3lVb）：S2.46 / F2.89 / T8.77% / R17.29%。Sharpe 更高，但收益被压到 17.29%，F 回落，说明质量腿 1.0 附近是拐点；
- 换 TOP2000（N8，WjY1Zzno）：S2.34 / F2.74 / T10.11% / R17.16%。扩大池子只稀释信号，没换来 Sharpe。

---

## 六、同期失败的方向（负结果也有信息量）

- 纯期权微观结构支线（PCR 持仓 / 成交量 / 盈亏平衡价 / 合成远期，8 条变体）：全灭，最高 S0.87 / F0.38。单一期权域字段在 TOP3000 上撑不起来，必须与基本面或价格腿复合。
- 社交媒体声量波动率支线：照公开样例复现 `-ts_std_dev(ts_backfill(scl12_buzz, 20), 20)`（SUBINDUSTRY / TOP3000），只拿到 S0.78 / F0.48，与样例宣称的 S1.47 / F1.67 差一个量级。换池子就失效，当"复现要留余量"的提醒。

---

## 七、可复用的三条结论

1. **先看 Fitness 公式的分母，再决定优化方向。** 换手 >12.5% 时，decay 是全套算子里性价比最高的一个；换手 <12.5% 后，降换手纯亏收益，要转头去抬 Sharpe / Returns。
2. **加腿优先加经济逻辑不同源的腿。** ROE（质量）、IV 溢价（期权情绪）与反转、前瞻 E/P 不同源，各加一档都在抬 S；而同属"财务困境"的杠杆类腿一加就撞相关性。
3. **压换手先试 decay，再试 truncation。** 本轮 truncation 三档全无变化，说明在 rank 线性复合下截断基本空转，别浪费时间。

12.5% 不是什么魔法数字，它只是公式里的一个常数。知道它在哪里，比多试 50 个变体更有用。
