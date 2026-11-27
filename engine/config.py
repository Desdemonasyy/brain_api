"""全局配置：路径、默认设置、闸门阈值、算子/字段白名单。

闸门阈值允许用 brain_api/gates.json 覆盖（浅合并 regions，深合并非 regions 段落）。
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / ".state"
DATA_DIR = ROOT / "data"
DB_PATH = Path(os.environ.get("BRAIN_LEDGER_DB", str(DATA_DIR / "ledger.db")))
GATES_PATH = ROOT / "gates.json"
REGIONS_PATH = ROOT / "regions.yaml"

API = "https://api.worldquantbrain.com"
HEADERS = {
    "Accept": "application/json;version=2.0",
    "Content-Type": "application/json",
}

# 与 brain.py 保持一致；候选加载时会被逐条覆盖
BASE_SETTINGS = {
    "instrumentType": "EQUITY",
    "region": "USA",
    "universe": "TOP3000",
    "delay": 1,
    "decay": 30,
    "neutralization": "INDUSTRY",
    "truncation": 0.01,
    "pasteurization": "ON",
    "nanHandling": "OFF",
    "unitHandling": "VERIFY",
    "language": "FASTEXPR",
    "visualization": False,
}

REGIONS = ["USA", "GLB", "EUR", "ASI", "CHN", "JPN", "KOR", "TWN", "HKG", "AMR"]
UNIVERSES = ["TOP3000", "TOP2000", "TOP1000", "TOP500", "TOP200", "TOPSP500", "MINVOL1M"]
NEUTRALIZATIONS = ["NONE", "MARKET", "SECTOR", "INDUSTRY", "SUBINDUSTRY", "COUNTRY"]

# 平台明确不可用或已被实测证伪的算子
FORBIDDEN_OPERATORS = {
    "ts_max": "平台报 unknown operator",
    "ts_min": "平台报 unknown operator",
    "ts_skewness": "平台报 unknown operator",
}

# 静态白名单，避免离线预检误杀；平台新增算子可缓存到 .state/operators.json
KNOWN_OPERATORS = {
    # 算术 / 逻辑
    "abs", "add", "and", "divide", "inverse", "log", "log_diff", "max", "min",
    "multiply", "not", "or", "power", "reverse", "sign", "signed_power", "sqrt",
    "subtract", "if_else", "is_nan", "nan_mask", "nan_out", "densify", "pasteurize",
    "purify", "replace", "convert", "filter",
    # 时序
    "ts_arg_max", "ts_arg_min", "ts_av_diff", "ts_backfill", "ts_corr", "ts_count_nans",
    "ts_covariance", "ts_decay_linear", "ts_delay", "ts_delta", "ts_ir", "ts_kurtosis",
    "ts_mean", "ts_median", "ts_product", "ts_quantile", "ts_rank", "ts_regression",
    "ts_returns", "ts_scale", "ts_std_dev", "ts_step", "ts_sum", "ts_zscore",
    "hump", "kth_element", "last_diff_value", "days_from_last_change", "inst_tvr",
    "jump_decay", "lag", "trade_when",
    # 截面
    "rank", "zscore", "scale", "normalize", "quantile", "winsorize", "bucket",
    # 分组
    "group_rank", "group_zscore", "group_neutralize", "group_mean", "group_sum",
    "group_scale", "group_backfill", "group_count", "group_max", "group_min",
    "group_std_dev", "group_median",
    # 向量
    "vec_avg", "vec_sum", "vec_ir", "vec_count", "vec_max", "vec_min",
    "vec_stddev", "vec_skewness", "vec_kurtosis", "vec_powersum", "vec_norm",
    "vec_range",
}

# 表达式里会出现的分组名 / 保留字，不做字段校验
GROUP_NAMES = {
    "market", "sector", "industry", "subindustry", "country", "exchange",
    "currency", "region", "universe",
}
RESERVED_WORDS = {
    "true", "false", "nan", "inf", "null", "and", "or", "not",
    "range", "filter", "rate", "scale",
}

# pv1 基础字段：字段目录通常只缓存了数据集文件，基础价量字段直接放行
BASE_FIELDS = {
    "open", "close", "high", "low", "volume", "returns", "vwap", "cap", "adv20",
    "sharesout", "dividend", "split", "assets", "liabilities", "equity", "sales",
    "income", "cashflow_op", "operating_income", "debt", "debt_lt", "debt_st",
    "inventory", "inventory_turnover", "receivable", "cash", "retained_earnings",
    "cashflow", "cashflow_fin", "cashflow_invst", "cashflow_dividends",
    "liabilities_curr", "assets_curr", "pretax_income", "income_beforeextra",
    "sales_growth", "sales_ps", "return_assets", "parkinson_volatility_120",
    "parkinson_volatility_20", "parkinson_volatility_30", "parkinson_volatility_60",
    "parkinson_volatility_90", "parkinson_volatility_180",
    "implied_volatility_call_30", "implied_volatility_call_60",
    "implied_volatility_call_90", "implied_volatility_call_180",
    "implied_volatility_call_270", "implied_volatility_call_360",
}

DEFAULT_GATES = {
    "precheck": {
        # 字段覆盖率低于该值只告警，不失败
        "min_field_coverage": 0.50,
        "max_decay": 512,
        "require_test_period_zero": True,
        # 表达式 group_* + 设置层中性化：默认只告警，严格模式可置 true
        "fail_on_double_neutralization": False,
    },
    "g3": {
        "min_sharpe": 1.25,
        "min_fitness": 1.00,
        # Delay-0 平台最低线更高：S≥2.0、F≥1.3
        "delay0_min_sharpe": 2.00,
        "delay0_min_fitness": 1.30,
        # 只用于报告「冲刺线」，不参与 PASS/FAIL
        "sprint_sharpe": 1.80,
        "sprint_fitness": 1.50,
        # 提交标准里的质量诊断项：不直接 FAIL，写入 detail 供人审
        "min_returns": 0.10,
        "drawdown_warn": 0.15,
        "min_long_count": 100,
        "min_short_count": 100,
    },
    "g4": {
        "min_turnover": 0.01,
        "max_turnover": 0.70,
        # Fitness 分母在 12.5% 处锁定，换手优先压到这条线以下
        "preferred_max_turnover": 0.125,
        "min_margin_bps": None,
    },
    "g5": {
        "min_years": 3,
        "positive_year_ratio": 0.80,
        "worst_year_sharpe": -0.50,
        "sub_universe_buffer": 1.05,
    },
    "g6": {
        "corr_threshold": 0.70,
        "self_exemption_multiplier": 1.10,
        "family_threshold": 0.95,
    },
    "g7": {
        "daily_submit_limit": 2,
        "require_competition_match": True,
        "approval_ttl_hours": 24,
    },
    # 区域级覆盖，未列出的区域沿用 g3 默认值
    "regions": {
        "USA": {},
        "GLB": {},
        "EUR": {},
        "ASI": {},
        "CHN": {},
        "JPN": {},
        "KOR": {},
        "TWN": {},
        "HKG": {},
        "AMR": {},
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_gates() -> dict:
    """加载闸门配置；gates.json 不存在时返回内置默认值。"""
    config = copy.deepcopy(DEFAULT_GATES)
    if GATES_PATH.exists():
        override = json.loads(GATES_PATH.read_text(encoding="utf-8"))
        config = _deep_merge(config, override)
    return config


_DEFAULT_REGIONS = {
    "defaults": {
        "delay": 1,
        "universe": "TOP3000",
        "neutralization": "SUBINDUSTRY",
        "min_sharpe": 1.25,
        "min_fitness": 1.0,
        "weight": 1.0,
    },
    "regions": {region: {} for region in REGIONS},
}


def load_regions() -> dict:
    """加载 regions.yaml；缺失时返回默认多区配置。"""
    if not REGIONS_PATH.exists():
        return copy.deepcopy(_DEFAULT_REGIONS)
    try:
        import yaml

        payload = yaml.safe_load(REGIONS_PATH.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        return copy.deepcopy(_DEFAULT_REGIONS)
    return _deep_merge(copy.deepcopy(_DEFAULT_REGIONS), payload)


def region_profile(region: str) -> dict:
    regions = load_regions()
    profile = dict(regions.get("defaults", {}))
    profile.update(regions.get("regions", {}).get(region, {}) or {})
    return profile


def region_g3(gates: dict, region: str) -> dict:
    merged = dict(gates["g3"])
    merged.update(gates.get("regions", {}).get(region, {}) or {})
    profile = region_profile(region)
    for key in ("min_sharpe", "min_fitness", "sprint_sharpe", "sprint_fitness"):
        if key in profile:
            merged[key] = profile[key]
    return merged
