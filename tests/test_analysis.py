"""Test analysis with mock data"""
import sys
import json
from datetime import datetime

def test_analysis(symbol: str = "AAPL"):
    """Test full analysis pipeline"""
    print(f"\n{'='*60}")
    print(f"Testing Analysis: {symbol}")
    print(f"{'='*60}\n")
    
    # Import after adding path
    sys.path.insert(0, str(__file__).rsplit('/', 2)[0])
    
    from finance_service.app import finance_service
    
    # Run analysis
    result = finance_service.analyze(symbol)
    
    # Display result
    print(json.dumps(result, indent=2))
    
    # Print summary
    if "error" not in result:
        print(f"\n{'='*60}")
        print(f"DECISION: {result.get('decision')} (Confidence: {result.get('confidence')})")
        print(f"REQUIRED APPROVAL: {result.get('required_approval')}")
        print(f"{'='*60}\n")
        
        if result.get('decision') != 'HOLD':
            pos = result.get('position', {})
            print(f"Position: {pos.get('action_qty')} shares @ ${pos.get('action_value', 0) / max(pos.get('action_qty', 1), 1):.2f}")
            
            risk = result.get('risk', {})
            print(f"Risk Level: {risk.get('risk_level')}")
            print(f"Max Loss: ${risk.get('max_loss_estimate')}")
            print(f"Stop Loss: ${risk.get('stop_loss')}")
            print(f"Take Profit: ${risk.get('take_profit')}\n")
    
    return result


if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    test_analysis(symbol)
