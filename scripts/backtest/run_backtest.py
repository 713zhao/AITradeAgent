#!/usr/bin/env python3
"""Backtesting CLI - Run strategy backtests from command line.

Usage:
    python3 run_backtest.py --strategy rule --start 2023-01-01 --end 2024-12-31 --symbols AAPL,MSFT
    python3 run_backtest.py --wfa --window 504 --step 63 --symbols SPY
    python3 run_backtest.py --optimize --param-file config/optimization_grid.yaml
"""
import argparse
import sys
import os
from pathlib import Path
import logging

# Add finance_service to path
sys.path.insert(0, str(Path(__file__).parent))

from finance_service.backtesting import BacktestEngine, load_data, RuleStrategyBacktest, load_rule_strategy, WalkForwardAnalyzer
from finance_service.core.yaml_config import get_config_engine

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="AITradeAgent Backtesting CLI")
    parser.add_argument("--strategy", choices=['rule', 'buy_and_hold'], default='rule', help="Strategy to backtest")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--symbols", required=True, help="Comma-separated list of symbols")
    parser.add_argument("--initial-capital", type=float, default=100000.0, help="Starting capital")
    parser.add_argument("--commission", type=float, default=0.0005, help="Commission (fraction)")
    parser.add_argument("--slippage", type=float, default=0.0002, help="Slippage (fraction)")
    parser.add_argument("--max-position-pct", type=float, default=10.0, help="Max position size %")
    parser.add_argument("--report-format", choices=['pdf', 'html'], default='pdf', help="Report format")
    parser.add_argument("--output-dir", default="storage/backtest_results", help="Output directory")
    
    # Optimization
    parser.add_argument("--optimize", action="store_true", help="Run grid search optimization")
    parser.add_argument("--param-file", help="YAML file with parameter grid for optimization")
    parser.add_argument("--metric", default="sharpe_ratio", help="Metric to maximize during optimization")

    # Walk-forward
    parser.add_argument("--wfa", action="store_true", help="Run walk-forward analysis")
    parser.add_argument("--window", type=int, default=504, help="Training window size (bars)")
    parser.add_argument("--step", type=int, default=63, help="Step size (bars)")

    args = parser.parse_args()

    # Prepare output dir
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load data
    symbols = [s.strip() for s in args.symbols.split(',')]
    logger.info(f"Loading data for {len(symbols)} symbols: {symbols}")
    data = load_data(symbols=symbols, start=args.start, end=args.end)

    # Initialize strategy
    if args.strategy == 'rule':
        # Load rules from config
        config_engine = get_config_engine()
        rule_file = config_engine.get("finance", "strategy/rule_file", default="config/rules.yaml")
        if not os.path.exists(rule_file):
            logger.error(f"Rules file not found: {rule_file}")
            sys.exit(1)
        strategy = load_rule_strategy(rule_file)
    else:  # buy_and_hold
        from finance_service.backtesting.benchmarks import BuyAndHoldStrategy
        strategy = BuyAndHoldStrategy(symbols=symbols)

    # Run based on mode
    if args.wfa:
        logger.info("Running walk-forward analysis")
        param_grid = {}
        if args.param_file:
            import yaml
            with open(args.param_file, 'r') as f:
                param_grid = yaml.safe_load(f).get('param_grid', {})
        else:
            # Default simple grid if not provided
            param_grid = {'dummy': [0]}  # no actual params for RuleStrategy yet
        
        analyzer = WalkForwardAnalyzer(
            data=data,
            strategy_class=lambda: strategy,  # factory
            param_grid=param_grid,
            train_window=args.window,
            test_window=args.step,
            step=args.step,
            objective_metric=args.metric,
            engine_kwargs={
                'initial_capital': args.initial_capital,
                'commission': args.commission,
                'slippage': args.slippage,
                'max_position_size_pct': args.max_position_pct / 100,
            },
        )
        wfa_result = analyzer.run()
        logger.info(f"WFA aggregate: {wfa_result.aggregate_metrics}")
        # Save results
        summary_file = output_dir / "wfa_summary.json"
        wfa_result.oos_metrics.to_json(summary_file, indent=2)
        logger.info(f"WFA results saved to {summary_file}")

    elif args.optimize:
        logger.info("Running parameter optimization (grid search)")
        if not args.param_file:
            logger.error("--param-file required for optimization")
            sys.exit(1)
        import yaml
        with open(args.param_file, 'r') as f:
            param_grid = yaml.safe_load(f).get('param_grid', {})
        # We'll do simple grid search manually (similar to WalkForwardAnalyzer but without windows)
        best_score = -float('inf')
        best_params = None
        best_results = None
        from itertools import product
        param_names = list(param_grid.keys())
        param_values = list(param_grid.values())
        combinations = [dict(zip(param_names, combo)) for combo in product(*param_values)]
        logger.info(f"Testing {len(combinations)} parameter combinations")
        for params in combinations:
            # For now, only RuleStrategy supports parameters (needs to be implemented)
            # Placeholder: create strategy with params
            # strategy = RuleStrategyBacktest(rules_config)  # expand with params
            # For now skip
            pass
        logger.info("Optimization not fully implemented for this strategy type yet")

    else:
        # Simple single backtest
        logger.info("Running single backtest")
        engine = BacktestEngine(
            initial_capital=args.initial_capital,
            commission=args.commission,
            slippage=args.slippage,
            max_position_size_pct=args.max_position_pct / 100,
        )
        results = engine.run(data, strategy)

        # Print summary
        print("\n=== Backtest Results ===")
        print(f"Initial Capital: ${args.initial_capital:,.2f}")
        print(f"Final Capital: ${results.final_capital:,.2f}")
        print(f"Total Return: {results.total_return_pct:.2%}")
        print(f"Sharpe Ratio: {results.metrics.get('sharpe_ratio', 0):.2f}")
        print(f"Max Drawdown: {results.metrics.get('max_drawdown', 0):.2%}")
        print(f"Win Rate: {results.metrics.get('win_rate', 0):.2%}")
        print(f"Total Trades: {len(results.trades)}")

        # Generate report
        report_path = output_dir / f"backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{args.report_format}"
        if args.report_format == 'pdf':
            generate_pdf_report(results, str(report_path))
        else:
            generate_html_report(results, str(report_path))
        print(f"Report saved to {report_path}")


if __name__ == "__main__":
    main()
