"""Walk-forward analysis (WFA) for strategy robustness testing.

Implements rolling/expanding window optimization and out-of-sample testing.
Measures strategy stability across different market regimes.
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional, Callable, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from .engine import BacktestEngine, BacktestResults
from .strategies import BacktestableStrategy

logger = logging.getLogger(__name__)


@dataclass
class WFAResult:
    """Results from walk-forward analysis"""
    oos_metrics: pd.DataFrame  # Metrics for each OOS window
    aggregate_metrics: Dict[str, float]  # Aggregated OOS performance
    consistency_score: float  # % of OOS windows with positive return
    best_params: Dict[str, Any]  # Best parameter set (by OOS avg)
    worst_params: Dict[str, Any]  # Worst parameter set
    window_details: List[Dict]  # Per-window details (params, train dates, test dates, metrics)


class WalkForwardAnalyzer:
    """Walk-forward analysis orchestrator.

    Args:
        data: Full historical dataset ( MultiIndex (date, symbol) or single symbol)
        strategy_class: Strategy class (callable) that accepts parameters
        param_grid: Dict of parameter names to list of values for grid search
        train_window: Number of bars for training window (e.g., 504 for 2 years)
        test_window: Number of bars for out-of-sample testing (e.g., 63 for 3 months)
        step: Step size between windows (usually = test_window)
        objective_metric: Metric to maximize during optimization ('sharpe_ratio', 'total_return_pct')
    """

    def __init__(
        self,
        data: pd.DataFrame,
        strategy_class: Callable[..., BacktestableStrategy],
        param_grid: Dict[str, List],
        train_window: int = 504,
        test_window: int = 63,
        step: int = 63,
        objective_metric: str = 'sharpe_ratio',
        engine_kwargs: Optional[Dict] = None,
    ):
        self.data = data
        self.strategy_class = strategy_class
        self.param_grid = param_grid
        self.train_window = train_window
        self.test_window = test_window
        self.step = step
        self.objective_metric = objective_metric
        self.engine_kwargs = engine_kwargs or {}

        # Determine date index
        if isinstance(data.index, pd.MultiIndex):
            self.dates = data.index.get_level_values(0).unique()
        else:
            self.dates = data.index

    def run(self) -> WFAResult:
        """Execute walk-forward analysis"""
        logger.info(f"Starting WFA: {len(self.dates)} dates, train={self.train_window}, test={self.test_window}, step={self.step}")

        window_details = []
        oos_metrics_list = []

        start_idx = 0
        while start_idx + self.train_window + self.test_window <= len(self.dates):
            train_start_date = self.dates[start_idx]
            train_end_date = self.dates[start_idx + self.train_window - 1]
            test_start_date = self.dates[start_idx + self.train_window]
            test_end_date = self.dates[start_idx + self.train_window + self.test_window - 1]

            logger.info(f"Window {len(window_details)+1}: Train {train_start_date.date()}–{train_end_date.date()}, Test {test_start_date.date()}–{test_end_date.date()}")

            # 1. Split data
            train_data = self.data.loc[train_start_date:train_end_date]
            test_data = self.data.loc[test_start_date:test_end_date]

            # 2. Optimize on training set (grid search)
            best_params, best_score = self._optimize(train_data)
            logger.debug(f"Best params: {best_params}, score={best_score:.3f}")

            # 3. Backtest best params on OOS (test set)
            strategy = self.strategy_class(**best_params)
            engine = BacktestEngine(**self.engine_kwargs)
            results = engine.run(test_data, strategy)
            metrics = results.metrics.copy()
            metrics['objective_score'] = metrics.get(self.objective_metric, 0.0)
            metrics['train_start'] = train_start_date
            metrics['train_end'] = train_end_date
            metrics['test_start'] = test_start_date
            metrics['test_end'] = test_end_date
            metrics['params'] = best_params
            oos_metrics_list.append(metrics)

            window_details.append({
                'train_start': train_start_date,
                'train_end': train_end_date,
                'test_start': test_start_date,
                'test_end': test_end_date,
                'params': best_params,
                'train_score': best_score,
                'oos_metrics': metrics,
            })

            start_idx += self.step

        if not oos_metrics_list:
            raise ValueError("No windows generated. Check dates and window sizes.")

        # Aggregate OOS performance
        oos_df = pd.DataFrame(oos_metrics_list)
        aggregate = {
            'avg_sharpe': oos_df['sharpe_ratio'].mean(),
            'avg_total_return': oos_df['total_return_pct'].mean(),
            'win_rate_pct_windows': (oos_df['total_return_pct'] > 0).mean() * 100,
            'avg_max_drawdown': oos_df['max_drawdown'].mean(),
            'consistency_score': (oos_df['total_return_pct'] > 0).mean(),
            'total_windows': len(oos_df),
        }

        # Best/worst params (by OOS objective)
        best_idx = oos_df['objective_score'].idxmax()
        worst_idx = oos_df['objective_score'].idxmin()
        best_params = oos_df.loc[best_idx, 'params']
        worst_params = oos_df.loc[worst_idx, 'params']

        logger.info(f"WFA complete: {len(oos_df)} windows, avg Sharpe={aggregate['avg_sharpe']:.2f}, consistency={aggregate['consistency_score']:.0%}")

        return WFAResult(
            oos_metrics=oos_df,
            aggregate_metrics=aggregate,
            consistency_score=aggregate['consistency_score'],
            best_params=best_params,
            worst_params=worst_params,
            window_details=window_details,
        )

    def _optimize(self, train_data: pd.DataFrame) -> Tuple[Dict, float]:
        """Grid search over parameter combinations on training set"""
        from itertools import product
        param_names = list(self.param_grid.keys())
        param_values = list(self.param_grid.values())
        combinations = [dict(zip(param_names, combo)) for combo in product(*param_values)]

        best_score = -np.inf
        best_params = None

        for params in combinations:
            strategy = self.strategy_class(**params)
            engine = BacktestEngine(**self.engine_kwargs)
            results = engine.run(train_data, strategy)
            score = results.metrics.get(self.objective_metric, -np.inf)
            if score > best_score:
                best_score = score
                best_params = params

        return best_params, best_score
