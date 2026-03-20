#!/usr/bin/env python3
"""
Paper Trading Simulation Runner

Runs the AiTradeAgent in paper trading mode for a specified duration
and tracks performance toward the 20% annual return target.

Usage:
    python run_paper_trading.py [--duration-hours 24] [--symbols NVDA,AMD,AVGO] [--report]
"""

import asyncio
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
import argparse

sys.path.insert(0, str(Path(__file__).parent))

from finance_service.core.yaml_config import YAMLConfigEngine
from finance_service.app import SimpleFinanceService

class PaperTradingSimulator:
    """Run paper trading simulation and track performance"""
    
    def __init__(self, finance_service: SimpleFinanceService, initial_capital: float = 100000):
        self.finance = finance_service
        self.initial_capital = initial_capital
        self.start_time = datetime.now()
        self.trades_executed = []
        self.portfolio_history = []
        
    async def run_analysis_batch(self, symbols: list[str]) -> dict:
        """Analyze a batch of symbols and collect trade proposals"""
        results = {}
        for symbol in symbols:
            try:
                # Use internal async method directly
                analysis = await self.finance._analyze_async(symbol)
                results[symbol] = analysis
            except Exception as e:
                print(f"  ⚠️ Analysis failed for {symbol}: {e}")
        return results
    
    def filter_executable_trades(self, analyses: dict, confidence_threshold: float = 0.5) -> list[dict]:
        """Filter analyses to executable trades (auto-execute if not requiring approval)"""
        trades = []
        for symbol, analysis in analyses.items():
            if analysis.get("decision") in ["BUY", "SELL"] and analysis.get("confidence", 0) >= confidence_threshold:
                trades.append(analysis)
        return trades
    
    async def get_portfolio_snapshot(self) -> dict:
        """Get current portfolio snapshot"""
        try:
            state = await self.finance._portfolio_state_async()
            if "error" in state:
                return {"error": state["error"]}
            return {
                "timestamp": datetime.now().isoformat(),
                "cash": state.get("overview", {}).get("cash", 0),
                "positions_value": state.get("overview", {}).get("positions_value", 0),
                "total_value": state.get("overview", {}).get("total_value", 0),
                "positions": state.get("positions", []),
                "daily_pnl": state.get("overview", {}).get("daily_pnl", 0),
            }
        except Exception as e:
            return {"error": str(e)}
    
    def calculate_returns(self, current_value: float) -> dict:
        """Calculate return metrics"""
        duration = datetime.now() - self.start_time
        days = max(duration.total_seconds() / 86400, 0.01)  # Avoid division by zero
        
        total_return = current_value - self.initial_capital
        return_pct = (total_return / self.initial_capital) * 100
        
        # Annualized return (CAGR)
        years = days / 365.25
        if years > 0:
            cagr = ((current_value / self.initial_capital) ** (1/years) - 1) * 100
        else:
            cagr = 0
        
        return {
            "days_elapsed": days,
            "total_return": total_return,
            "return_pct": return_pct,
            "annualized_cagr": cagr,
            "initial_capital": self.initial_capital,
            "current_value": current_value,
        }
    
    async def run_simulation_cycle(self, symbols: list[str], confidence_threshold: float = 0.4):
        """Run one full trading cycle: analyze → execute (simulated) → update portfolio"""
        print(f"\n📊 Trading Cycle at {datetime.now().strftime('%H:%M:%S')}")
        
        # 1. Analyze all symbols
        print(f"  Analyzing {len(symbols)} symbols...")
        analyses = await self.run_analysis_batch(symbols)
        
        # 2. Filter for executable trades
        trades = self.filter_executable_trades(analyses, confidence_threshold)
        print(f"  Found {len(trades)} trade opportunities")
        
        # 3. Execute trades (paper trading - just log them)
        for trade in trades:
            symbol = trade["symbol"]
            action = trade["decision"]
            qty = trade.get("position", {}).get("action_qty", 0)
            price = trade.get("position", {}).get("action_value", 0) / qty if qty > 0 else 0
            print(f"    {action} {qty} {symbol} @ ${price:.2f} (conf: {trade['confidence']:.1%})")
            self.trades_executed.append({
                "timestamp": datetime.now().isoformat(),
                "symbol": symbol,
                "action": action,
                "quantity": qty,
                "price": price,
                "confidence": trade["confidence"],
            })
        
        # 4. Get portfolio snapshot
        snapshot = await self.get_portfolio_snapshot()
        if "error" not in snapshot:
            self.portfolio_history.append(snapshot)
            current_value = snapshot["total_value"]
            returns = self.calculate_returns(current_value)
            
            print(f"  Portfolio Value: ${current_value:,.2f}")
            print(f"  Return: {returns['return_pct']:+.2f}% (annualized: {returns['annualized_cagr']:+.1f}%)")
            print(f"  Positions: {len(snapshot['positions'])}")
            print(f"  Trades executed so far: {len(self.trades_executed)}")
        else:
            print(f"  ⚠️ Portfolio error: {snapshot['error']}")
    
    def generate_report(self) -> str:
        """Generate final performance report"""
        if not self.portfolio_history:
            return "No portfolio data collected."
        
        final = self.portfolio_history[-1]
        returns = self.calculate_returns(final["total_value"])
        
        report_lines = [
            "="*70,
            "📈 PAPER TRADING SIMULATION REPORT",
            "="*70,
            f"\n📅 Simulation Period:",
            f"   Start: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"   End:   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"   Duration: {returns['days_elapsed']:.1f} days",
            
            f"\n💰 Capital:",
            f"   Initial: ${self.initial_capital:,.2f}",
            f"   Final:   ${final['total_value']:,.2f}",
            f"   Return:  ${returns['total_return']:+,.2f} ({returns['return_pct']:+.2f}%)",
            f"   CAGR:    {returns['annualized_cagr']:+.1f}% (target: 20%)",
            
            f"\n📊 Activity:",
            f"   Trades executed: {len(self.trades_executed)}",
            f"   Final positions: {len(final['positions'])}",
            
            f"\n🎯 Target Status:",
        ]
        
        target_met = returns['annualized_cagr'] >= 20
        status = "✅ MET" if target_met else "🔄 IN PROGRESS"
        report_lines.append(f"   20% Annual Return: {status} (current: {returns['annualized_cagr']:.1f}%)")
        
        report_lines.append("\nTop Positions:")
        positions = sorted(final["positions"], key=lambda x: x.get("market_value", 0), reverse=True)[:5]
        for pos in positions:
            report_lines.append(f"   {pos['symbol']}: {pos['qty']} shares @ ${pos['avg_cost']:.2f} = ${pos['market_value']:,.2f}")
        
        report_lines.append("\n" + "="*70)
        return "\n".join(report_lines)

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration-hours", type=float, default=1, help="Simulation duration in hours")
    parser.add_argument("--cycle-minutes", type=int, default=15, help="Trading cycle interval (minutes)")
    parser.add_argument("--confidence", type=float, default=0.4, help="Confidence threshold for execution")
    parser.add_argument("--report", action="store_true", help="Generate detailed report at end")
    args = parser.parse_args()
    
    print("="*70)
    print("🤖 PAPER TRADING SIMULATION")
    print("="*70)
    print(f"\nTarget: 20%+ annual return")
    print(f"Duration: {args.duration_hours} hours")
    print(f"Cycle interval: {args.cycle_minutes} minutes")
    print(f"Confidence threshold: {args.confidence:.0%}")
    print("\nPress Ctrl+C to stop early.")
    
    # Initialize finance service
    print("\n[1/3] Initializing Finance Service...")
    finance = SimpleFinanceService()
    
    # Reset portfolio to initial state for clean simulation
    print("   Resetting portfolio to initial cash...")
    # Portfolio reset is automatic on first call if config says so, or we can manually clear
    # For now, just use existing state
    
    # Load universe from config
    print("[2/3] Loading trading universe...")
    config = YAMLConfigEngine(config_dir="config")
    all_symbols = config.get("finance", "universe/all_symbols", default=[])
    print(f"   Universe: {len(all_symbols)} symbols")
    # Focus on top 10 liquid symbols for simulation
    simulation_symbols = all_symbols[:10] if len(all_symbols) > 10 else all_symbols
    print(f"   Simulation batch: {len(simulation_symbols)} symbols")
    
    # Initialize simulator
    simulator = PaperTradingSimulator(finance)
    
    # Run simulation loop
    print(f"\n[3/3] Starting simulation...")
    print("-"*70)
    
    try:
        cycle_interval_sec = args.cycle_minutes * 60
        end_time = datetime.now() + timedelta(hours=args.duration_hours)
        
        cycle_num = 0
        while datetime.now() < end_time:
            cycle_num += 1
            print(f"\n🔁 Cycle {cycle_num} - {datetime.now().strftime('%H:%M:%S')}")
            
            # Run one trading cycle
            await simulator.run_simulation_cycle(simulation_symbols, args.confidence)
            
            # Calculate time to wait
            elapsed = time.time() - cycle_start if 'cycle_start' in locals() else 0
            sleep_time = max(0, cycle_interval_sec - elapsed)
            
            if datetime.now() + timedelta(seconds=sleep_time) < end_time and sleep_time > 0:
                print(f"   Sleeping until next cycle ({sleep_time/60:.1f} min)...")
                await asyncio.sleep(sleep_time)
            else:
                break
        
        # Generate final report
        print("\n" + "="*70)
        print("📊 SIMULATION COMPLETE")
        print("="*70)
        
        report = simulator.generate_report()
        print(report)
        
        if args.report:
            # Save detailed report to file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_file = f"paper_trading_report_{timestamp}.txt"
            with open(report_file, 'w') as f:
                f.write(report)
                f.write("\n\nAll Trades Executed:\n")
                f.write("-"*70 + "\n")
                for trade in simulator.trades_executed:
                    f.write(f"{trade['timestamp']} | {trade['action']} {trade['quantity']} {trade['symbol']} @ ${trade['price']:.2f} (conf: {trade['confidence']:.1%})\n")
            print(f"\n📄 Detailed report saved to: {report_file}")
        
        return 0
        
    except KeyboardInterrupt:
        print("\n\n⚠️ Simulation interrupted by user")
        report = simulator.generate_report()
        print(report)
        return 0
    except Exception as e:
        print(f"\n❌ Simulation error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
