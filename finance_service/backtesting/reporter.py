"""Report generation for backtest results.

Generates PDF/HTML reports with equity curves, drawdown charts, monthly returns heatmap,
and performance metrics table.
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from typing import Optional
import logging
from datetime import datetime
from .metrics import monthly_returns_heatmap

logger = logging.getLogger(__name__)


def generate_pdf_report(
    results,
    output_path: str,
    benchmark_equity: Optional[pd.Series] = None,
    title: str = "Backtest Report",
) -> None:
    """
    Generate a multi-page PDF report.

    Args:
        results: BacktestResults object
        output_path: Output PDF file path
        benchmark_equity: Optional benchmark equity series for comparison
        title: Report title
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with PdfPages(output_path) as pdf:
        # Page 1: Equity curve & drawdown
        fig, axes = plt.subplots(2, 1, figsize=(11, 8), sharex=True)
        equity = results.portfolio_history['equity']
        axes[0].plot(equity.index, equity.values, label='Strategy', linewidth=2)
        if benchmark_equity is not None:
            axes[0].plot(benchmark_equity.index, benchmark_equity.values, label='Benchmark', linestyle='--')
        axes[0].set_ylabel('Equity ($)')
        axes[0].set_title(f'{title} — Equity Curve')
        axes[0].legend()
        axes[0].grid(True, alpha=0.3)

        # Drawdown
        running_max = equity.expanding().max()
        dd = (equity - running_max) / running_max
        axes[1].fill_between(dd.index, dd.values * 100, 0, color='red', alpha=0.3)
        axes[1].set_ylabel('Drawdown (%)')
        axes[1].set_xlabel('Date')
        axes[1].grid(True, alpha=0.3)
        plt.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

        # Page 2: Monthly returns heatmap
        fig, ax = plt.subplots(figsize=(9, 4))
        heatmap = monthly_returns_heatmap(equity)
        im = ax.imshow(heatmap.values, cmap='RdYlGn', aspect='auto', vmin=-0.10, vmax=0.10)
        ax.set_xticks(range(len(heatmap.columns)))
        ax.set_xticklabels(heatmap.columns)
        ax.set_yticks(range(len(heatmap.index)))
        ax.set_yticklabels([str(y) for y in heatmap.index])
        ax.set_xlabel('Month')
        ax.set_ylabel('Year')
        ax.set_title('Monthly Returns (%)')
        plt.colorbar(im, ax=ax, format='%.1%')
        plt.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

        # Page 3: Metrics table
        fig, ax = plt.subplots(figsize=(9, 6))
        ax.axis('tight')
        ax.axis('off')
        metrics = results.metrics
        table_data = [
            ('Total Return', f"{metrics.get('total_return_pct', 0):.2%}"),
            ('CAGR', f"{metrics.get('cagr', 0):.2%}"),
            ('Sharpe Ratio', f"{metrics.get('sharpe_ratio', 0):.2f}"),
            ('Sortino Ratio', f"{metrics.get('sortino_ratio', 0):.2f}"),
            ('Calmar Ratio', f"{metrics.get('calmar_ratio', 0):.2f}"),
            ('Max Drawdown', f"{metrics.get('max_drawdown', 0):.2%}"),
            ('Win Rate', f"{metrics.get('win_rate', 0):.2%}"),
            ('Profit Factor', f"{metrics.get('profit_factor', 0):.2f}"),
            ('Expectancy ($)', f"${metrics.get('expectancy', 0):,.2f}"),
            ('Avg Holding (days)', f"{metrics.get('avg_holding_period_days', 0):.1f}"),
            ('Total Trades', f"{metrics.get('total_trades', 0)}"),
        ]
        table = ax.table(cellText=table_data, loc='center', cellLoc='left')
        table.auto_set_font_size(False)
        table.set_fontsize(12)
        ax.set_title('Performance Metrics')
        pdf.savefig(fig)
        plt.close(fig)

        # Metadata
        pdf.infodict()['Title'] = title
        pdf.infodict()['CreationDate'] = datetime.now()

    logger.info(f"Report saved to {output_path}")


def generate_html_report(
    results,
    output_path: str,
    benchmark_equity: Optional[pd.Series] = None,
) -> None:
    """
    Generate an interactive HTML report using plotly.
    (Stub for future enhancement)
    """
    raise NotImplementedError("HTML report with plotly not yet implemented")
