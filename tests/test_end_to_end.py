"""End-to-end integration test"""
import sys
import json
from uuid import uuid4

def test_end_to_end():
    """Test full flow: analyze → propose → execute"""
    print(f"\n{'='*60}")
    print("End-to-End Integration Test")
    print(f"{'='*60}\n")
    
    sys.path.insert(0, str(__file__).rsplit('/', 2)[0])
    
    from finance_service.app import finance_service
    from finance_service.tools.approval_gate import ManualApprovalGate
    
    symbol = "AAPL"
    
    # Step 1: Analyze
    print(f"Step 1: Analyze {symbol}")
    print("-" * 60)
    analysis = finance_service.analyze(symbol)
    
    if "error" in analysis:
        print(f"❌ Analysis failed: {analysis['error']}")
        return
    
    print(f"✅ Analysis complete")
    print(f"   Decision: {analysis.get('decision')}")
    print(f"   Confidence: {analysis.get('confidence')}")
    print(f"   Requires Approval: {analysis.get('required_approval')}")
    
    task_id = analysis.get('task_id')
    
    if analysis.get('decision') == 'HOLD':
        print(f"\n⚠️  HOLD decision - no trade proposed")
        return
    
    # Step 2: Propose Trade
    print(f"\nStep 2: Propose Trade")
    print("-" * 60)
    proposal = finance_service.portfolio_propose_trade(analysis)
    
    print(f"✅ Proposal created")
    print(f"   Valid: {proposal.get('valid')}")
    print(f"   Summary: {proposal.get('summary')}")
    
    if not proposal.get('valid'):
        print(f"\n❌ Proposal validation failed")
        errors = proposal.get('details', {}).get('validation', {}).get('errors', [])
        for error in errors:
            print(f"   - {error}")
        return
    
    # Step 3: Request Approval
    print(f"\nStep 3: Request Approval")
    print("-" * 60)
    
    gate = ManualApprovalGate()
    approved, msg, approval_id = gate.request_approval(
        task_id,
        proposal.get('summary'),
        proposal.get('details')
    )
    
    if not approved:
        print(f"❌ Approval denied: {msg}")
        return
    
    print(f"✅ {msg}")
    
    # Step 4: Execute Trade
    print(f"\nStep 4: Execute Trade")
    print("-" * 60)
    execution = finance_service.portfolio_execute_trade(task_id, approval_id)
    
    print(f"✅ Trade executed")
    print(f"   Success: {execution.get('success')}")
    print(f"   Message: {execution.get('message')}")
    
    # Step 5: Display Final State
    print(f"\nStep 5: Final Portfolio State")
    print("-" * 60)
    final_state = finance_service.portfolio_get_state()
    
    print(f"Cash: ${final_state['cash']:.2f}")
    print(f"Equity: ${final_state['equity']:.2f}")
    print(f"Total Value: ${final_state['total_value']:.2f}")
    
    print(f"\nPositions:")
    for sym, pos in final_state['positions'].items():
        print(f"  {sym}:")
        print(f"    Qty: {pos['qty']}")
        print(f"    Current Price: ${pos['current_price']:.2f}")
        print(f"    Market Value: ${pos['market_value']:.2f}")
        print(f"    Unrealized PnL: ${pos['unrealized_pnl']:.2f}")
    
    print(f"\n{'='*60}")
    print(f"✅ END-TO-END TEST PASSED")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    test_end_to_end()
