# WorldQuant BRAIN 本地文档库

来源：`https://github.com/anweat/worldquantAlpha-dev/tree/main/docs`
本地副本：`d:\workfile\2026\brain_api\docs\worldquantAlpha-dev`
全局副本：`C:\Users\sharon.zhong\.trae-cn\skills\brain-alpha-pipeline\references\worldquantAlpha-dev`

> 任何 WorldQuant 相关项目都可以直接读这个目录；引擎侧的 `docs/operators_reference.md` 和 `docs/submission_standards.md` 是 03/05 的快捷副本。

## 核心文档

| 编号 | 文档 | 内容 |
|---|---|---|
| 00 | [从零理解 BRAIN 平台与 FE 表达式](00_从零理解BRAIN平台与FE表达式.md) | 平台、Alpha、FE 表达式入门 |
| 01 | [量化交易与 BRAIN 平台概述](01_量化交易与BRAIN平台概述.md) | 平台定位、数据、工作流 |
| 02 | [Fast Expression 语言指南](02_Fast_Expression_语言指南.md) | FE 语法、变量、控制流 |
| 03 | [运算符完整参考手册](03_运算符完整参考手册.md) | 66 个运算符 / 7 类 |
| 04 | [模拟设置详解](04_模拟设置详解.md) | Region / Universe / Delay / Neutralization / Decay / Truncation |
| 05 | [性能指标与提交标准](05_性能指标与提交标准.md) | Sharpe / Fitness / Turnover / 8 项 IS checks |
| 06 | [数据字段与数据集](06_数据字段与数据集.md) | Data Explorer、覆盖率、向量字段、backfill |
| 07 | [Alpha 开发实战指南](07_Alpha开发实战指南.md) | 从想法到表达式到回测 |
| 08 | [API 接口与自动化脚本](08_API接口与自动化脚本.md) | 登录、模拟、轮询、提交 |
| 09 | [学习路径与 Challenge 得分指南](09_学习路径与Challenge得分指南.md) | 学习路线、得分规则 |
| 10 | [实战 Alpha 测试报告](10_实战Alpha测试报告.md) | 实测案例与指标解读 |
| 11 | [进阶 Alpha 知识与策略](11_进阶Alpha知识与策略.md) | 进阶信号、组合、风险 |
| 12 | [社区洞察与 Alpha 经验](12_community_insights_and_alpha_experience.md) | 社区经验汇总 |
| 13 | [Alpha 缺陷与社区智慧](13_alpha_defects_and_community_wisdom.md) | 常见缺陷、失败模式 |

## 工程架构文档

`architecture/` 下的文档描述的是该仓库自己的 Agent/Bus/Simulation Pool 架构，不是 BRAIN 平台规则；需要参考自动化实现时再读。

- [AGENT_INTERFACE](architecture/AGENT_INTERFACE.md)
- [AI_DISPATCHER](architecture/AI_DISPATCHER.md)
- [BUS_ARCHITECTURE](architecture/BUS_ARCHITECTURE.md)
- [COMPOSITION_RECIPES](architecture/COMPOSITION_RECIPES.md)
- [EVENT_CATALOG](architecture/EVENT_CATALOG.md)
- [EXPORT_FORMATS](architecture/EXPORT_FORMATS.md)
- [SIMULATION_POOL](architecture/SIMULATION_POOL.md)
- [TRACE_AS_TASK](architecture/TRACE_AS_TASK.md)

## 快速使用

```powershell
# 运算符搜索
python -m engine.cli ops regression

# 本地文档列表 / 搜索
python -m engine.cli docs
python -m engine.cli docs 数据字段

# 数据字段探索（读 .state/fields_*.json 缓存）
python -m engine.cli data
python -m engine.cli data sentiment --min-coverage 0.8
python -m engine.cli data --dataset model16
```
