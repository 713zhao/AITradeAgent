#!/usr/bin/env python3
"""
Test script to simulate a BUY trade proposal that requires approval.
"""

import asyncio
import logging
import sys
from datetime import datetime
from typing import Dict, Any

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

sys.path.insert(0, '/home/eric/.openclaw/workspace/AITradeAgent')

from finance_service.tools.approval_gate import get_approval_gate
from finance_service.agents.telegram_agent import TelegramAgent


async def simulate_buy_proposal() -> Dict[str, Any]:
    print("\n" + "="*70)
    print("🚀 TRADE PROPOSAL SIMULATION")
    print("="*70)
    
    proposal = {
        "symbol": "AAPL",
        "action": "BUY",
        "quantity": 50,
        "target_price": 182.43,
        "stop_loss_price": 175.00,
        "take_profit_price": 195.00,
        "confidence": 0.65,
        "rationale": "Technical breakout above 50-day MA with strong volume",
    }
    
    print("\n📊 **Strategy Generated BUY Proposal:**")
    print(f"  Symbol:        {proposal['symbol']}")
    print(f"  Action:        {proposal['action']}")
    print(f"  Quantity:      {proposal['quantity']} shares")
    print(f"  Target Price:  ${proposal['target_price']:.2f}")
    print(f"  Stop Loss:     ${proposal['stop_loss_price']:.2f}")
    print(f"  Take Profit:   ${proposal['take_profit_price']:.2f}")
    print(f"  Confidence:    {proposal['confidence']*100:.1f}%")
    print(f"  Rationale:     {proposal['rationale']}")
    
    return proposal


async def simulate_risk_assessment(proposal: Dict[str, Any]) -> Dict[str, Any]:
    print("\n" + "="*70)
    print("🔍 RISK ASSESSMENT")
    print("="*70)
    
    confidence = proposal['confidence']
    threshold = 0.75
    approval_required = confidence < threshold
    
    assessment = {
        "symbol": proposal['symbol'],
        "confidence": confidence,
        "passed": True,
        "approval_required": approval_required,
        "violations": ["Confidence 65.0% below threshold 75.0%"] if approval_required else [],
    }
    
    if approval_required:
        print(f"\n⚠️  **APPROVAL REQUIRED**")
        print(f"  Confidence: {confidence*100:.1f}% < Threshold: {threshold*100:.1f}%")
    else:
        print(f"\n✅ **OK TO AUTO-EXECUTE**")
        print(f"  Confidence: {confidence*100:.1f}% >= Threshold: {threshold*100:.1f}%")
    
    return assessment


async def send_telegram_approval_request(proposal: Dict[str, Any], risk: Dict[str, Any]) -> tuple:
    print("\n" + "="*70)
    print("📱 TELEGRAM APPROVAL NOTIFICATION")
    print("="*70)
    
    try:
        approval_gate = get_approval_gate("telegram")
        
        if not approval_gate.enabled:
            print("\n❌ Telegram approval gate is NOT enabled")
            return False, "Telegram not configured"
        
        details = {
            "symbol": proposal['symbol'],
            "quantity": proposal['quantity'],
            "price": proposal['target_price'],
            "confidence": risk['confidence'],
            "violations": risk.get('violations', []),
            "stop_loss": proposal.get('stop_loss_price'),
        }
        
        task_id = f"TEST_BUY_{proposal['symbol']}_{int(datetime.utcnow().timestamp())}"
        proposal_summary = f"BUY {proposal['quantity']} {proposal['symbol']} @ ${proposal['target_price']:.2f}"
        
        print(f"\n📤 Sending approval request to Telegram...")
        print(f"   Task ID: {task_id}")
        print(f"   Proposal: {proposal_summary}")
        print(f"   Timeout: 300 seconds")
        print(f"\n   👉 CHECK YOUR TELEGRAM for approval buttons!")
        print(f"   Click ✅ APPROVE or ❌ REJECT button\n")
        
        approved, response_msg = await approval_gate.request_approval(
            task_id=task_id, 
            proposal_summary=proposal_summary,
            details=details
        )
        
        if approved:
            print(f"\n✅ Approval response received!")
            print(f"   Response: {response_msg}")
            return True, response_msg
        else:
            print(f"\n❌ Approval rejected or timed out")
            print(f"   Response: {response_msg}")
            return False, response_msg
            
    except Exception as e:
        logger.error(f"Error in telegram approval: {e}", exc_info=True)
        print(f"\n❌ Error: {e}")
        return False, str(e)


async def execute_trade(proposal: Dict[str, Any]) -> Dict[str, Any]:
    print("\n" + "="*70)
    print("✅ TRADE EXECUTION")
    print("="*70)
    
    execution_result = {
        "trade_id": f"EXEC_{proposal['symbol']}_{int(datetime.utcnow().timestamp())}",
        "symbol": proposal['symbol'],
        "action": proposal['action'],
        "quantity": proposal['quantity'],
        "filled_price": proposal['target_price'],
        "status": "FILLED",
        "timestamp": datetime.utcnow().isoformat(),
        "stop_loss": proposal.get('stop_loss_price'),
        "take_profit": proposal.get('take_profit_price')
    }
    
    print(f"\n📈 **Trade Filled**")
    print(f"  Trade ID:     {execution_result['trade_id']}")
    print(f"  Symbol:       {execution_result['symbol']}")
    print(f"  Action:       {execution_result['action']}")
    print(f"  Quantity:     {execution_result['quantity']} shares")
    print(f"  Filled Price: ${execution_result['filled_price']:.2f}")
    print(f"  Stop Loss:    ${execution_result['stop_loss']:.2f}")
    print(f"  Take Profit:  ${execution_result['take_profit']:.2f}")
    
    return execution_result


async def main():
    print("\n" + "╔" + "="*68 + "╗")
    print("║ " + " "*15 + "TRADE APPROVAL WORKFLOW SIMULATOR" + " "*21 + "║")
    print("║ " + " "*10 + "Testing Telegram Notification & Approval Buttons" + " "*10 + "║")
    print("╚" + "="*68 + "╝")
    
    try:
        proposal = await simulate_buy_proposal()
        risk = await simulate_risk_assessment(proposal)
        
        if not risk['approval_required']:
            print("\n✅ Trade would auto-execute (no approval needed)")
            result = await execute_trade(proposal)
            return
        
        approved, message = await send_telegram_approval_request(proposal, risk)
        
        print("\n" + "="*70)
        if approved:
            print("👤 USER RESPONSE: ✅ APPROVED")
            print(f"   Message: {message}")
            result = await execute_trade(proposal)
            print(f"\n🎉 **WORKFLOW COMPLETE**")
            print(f"   Trade successfully executed after manual approval")
            print(f"   - Trade ID: {result['trade_id']}")
        else:
            print("👤 USER RESPONSE: ❌ REJECTED")
            print(f"   Message: {message}")
            print(f"\n❌ **TRADE CANCELLED**")
        
        print("\n" + "="*70)
        print("✅ Approval workflow simulation complete!")
        print("="*70 + "\n")
        
    except KeyboardInterrupt:
        print("\n\n⏹️  Simulation cancelled by user")
    except Exception as e:
        logger.error(f"Error in simulation: {e}", exc_info=True)
        print(f"\n❌ Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
