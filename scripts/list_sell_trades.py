import sys
import os
import argparse
from datetime import datetime, timedelta, timezone

# Add root directory to python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from finance_service.storage.database import get_portfolio_db

def parse_args():
    parser = argparse.ArgumentParser(description="List historical SELL trades.")
    parser.add_argument(
        '--period', 
        choices=['today', '1w', '1m', '1y', 'all'], 
        default='all',
        help='Time period to filter trades (default: all)'
    )
    return parser.parse_args()

def main():
    args = parse_args()
    
    # Calculate threshold date
    now = datetime.now(timezone.utc)
    threshold_date = None
    
    if args.period == 'today':
        threshold_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif args.period == '1w':
        threshold_date = now - timedelta(days=7)
    elif args.period == '1m':
        threshold_date = now - timedelta(days=30)
    elif args.period == '1y':
        threshold_date = now - timedelta(days=365)
        
    try:
        db = get_portfolio_db()
        trades = db.load_all_trade_objects()
        
        sell_trades = [t for t in trades if t.get('side', '').upper() == 'SELL']
        
        # Sort by ordered_at descending
        sell_trades.sort(key=lambda x: x.get('ordered_at', ''), reverse=True)
        
        filtered_trades = []
        for trade in sell_trades:
            date_str = trade.get('ordered_at', '')
            try:
                date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                if date_obj.tzinfo is None:
                    date_obj = date_obj.replace(tzinfo=timezone.utc)
            except:
                continue
                
            if threshold_date and date_obj < threshold_date:
                continue
                
            filtered_trades.append((trade, date_obj))

        if not filtered_trades:
            print(f"No SELL trades found for period: {args.period}")
            return

        print(f"--- Sell History ({args.period.upper()}) ---")
        print(f"Total Sell Trades: {len(filtered_trades)}\n")
        
        total_pnl = 0.0
        
        # Formatting output
        print(f"{'DATE':<20} | {'SYM':<6} | {'QTY':>5} | {'PRICE':>9} | {'P&L ($)':>10} | {'P&L (%)':>8} | {'REASON'}")
        print("-" * 90)
        
        for trade, date_obj in filtered_trades:
            date = date_obj.strftime('%Y-%m-%d %H:%M:%S')
            symbol = trade.get('symbol', 'UNKNOWN')
            
            price_val = trade.get('price', 0)
            price = f"${price_val:.2f}" if price_val else "$0.00"
            
            qty_val = trade.get('filled_quantity', trade.get('quantity', 0))
            qty = f"{int(qty_val)}" if qty_val else "0"
            
            # To get accurate PnL, we need to find the avg_cost of this position right before this sell
            # For simplicity if the system doesn't store realized_pnl on the trade object directly,
            # we will search backward for BUY orders of the same symbol to calculate average cost.
            buys = [t for t in trades if t.get('side', '').upper() == 'BUY' and t.get('symbol') == symbol]
            buys.sort(key=lambda x: x.get('ordered_at', ''))
            
            avg_cost = 0.0
            total_qty = 0
            for b in buys:
                b_date = datetime.fromisoformat(b.get('ordered_at', '').replace('Z', '+00:00'))
                if b_date.tzinfo is None:
                    b_date = b_date.replace(tzinfo=timezone.utc)
                    
                if b_date < date_obj:
                    b_qty = b.get('filled_quantity', b.get('quantity', 0))
                    b_price = b.get('price', 0)
                    new_qty = total_qty + b_qty
                    if new_qty > 0:
                        avg_cost = (total_qty * avg_cost + b_qty * b_price) / new_qty
                        total_qty = new_qty
                        
            pnl = 0.0
            pnl_pct = 0.0
            if avg_cost > 0:
                pnl = (price_val - avg_cost) * qty_val
                pnl_pct = ((price_val - avg_cost) / avg_cost) * 100
                
            total_pnl += pnl
                
            pnl_str = f"${pnl:.2f}"
            if pnl > 0: pnl_str = f"+{pnl_str}"
            
            pnl_pct_str = f"{pnl_pct:.2f}%"
            if pnl_pct > 0: pnl_pct_str = f"+{pnl_pct_str}"
            
            reason = trade.get('reason', 'Strategy exit')
            # Shorten reason if it's too long
            if len(reason) > 25:
                reason = reason[:22] + "..."
            
            print(f"[{date}] {symbol:<6} | {qty:>5} | {price:>9} | {pnl_str:>10} | {pnl_pct_str:>8} | {reason}")
            
        print("-" * 90)
        pnl_sign = "+" if total_pnl >= 0 else ""
        print(f"Total Period P&L: {pnl_sign}${total_pnl:,.2f}")

    except Exception as e:
        print(f"Error accessing trades: {e}")

if __name__ == "__main__":
    main()
