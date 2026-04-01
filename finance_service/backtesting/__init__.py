"""Backtesting package.

Main exports:
- BacktestEngine
- BacktestResults
- load_data
- RuleStrategyBacktest
- WalkForwardAnalyzer
- metrics
- benchmarks
"""
from .engine import BacktestEngine, BacktestResults, Trade
from .data_loader import load_data
from .strategies import BacktestableStrategy, RuleStrategyBacktest, load_rule_strategy
from .walk_forward import WalkForwardAnalyzer, WFAResult
from .metrics import calculate_metrics, monthly_returns_heatmap
from .benchmarks import BuyAndHoldStrategy, SPYBenchmark, VolatilityTargetedStrategy
from .reporter import generate_pdf_report, generate_html_report

__all__ = [
    'BacktestEngine',
    'BacktestResults',
    'Trade',
    'load_data',
    'BacktestableStrategy',
    'RuleStrategyBacktest',
    'load_rule_strategy',
    'WalkForwardAnalyzer',
    'WFAResult',
    'calculate_metrics',
    'monthly_returns_heatmap',
    'BuyAndHoldStrategy',
    'SPYBenchmark',
    'VolatilityTargetedStrategy',
    'generate_pdf_report',
    'generate_html_report',
]
