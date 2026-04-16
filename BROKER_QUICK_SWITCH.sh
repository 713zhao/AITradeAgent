#!/bin/bash
# Quick Script to Switch Between Paper and Real Trading

PROJECT_DIR="/home/claw.zhao/.openclaw/workspace/AITradeAgent"
CONFIG_FILE="$PROJECT_DIR/config/finance.yaml"
ENV_FILE="$PROJECT_DIR/.env"

echo "================================================"
echo "  AITradeAgent Broker Configuration Switcher"
echo "================================================"
echo ""

# Show current configuration
echo "📊 Current Configuration:"
echo "   File: $CONFIG_FILE"
CURRENT_BROKER=$(grep -A 1 "^execution:" "$CONFIG_FILE" | grep "broker:" | awk '{print $2}')
echo "   Current Broker: $CURRENT_BROKER"
echo ""

# Menu
echo "Choose an option:"
echo "1. Switch to Paper Trading (Safe Testing)"
echo "2. Switch to Tiger Brokers (Real Trading)"
echo "3. Show Broker Configuration"
echo "4. Test Broker Connection"
echo "0. Exit"
echo ""
read -p "Enter choice [0-4]: " choice

case $choice in
  1)
    echo "🔄 Switching to Paper Trading..."
    python3 << 'PYTHON'
import yaml

with open('config/finance.yaml', 'r') as f:
    config = yaml.safe_load(f)

config['execution']['broker'] = 'paper'
config['execution']['broker_config'] = {
    'paper': {
        'initial_cash': 100000.0,
        'slippage_bps': 1.0,
        'fill_delay_seconds': 1.0,
        'simulate_partial_fills': False
    }
}

with open('config/finance.yaml', 'w') as f:
    yaml.dump(config, f, default_flow_style=False, sort_keys=False)

print("✅ Switched to Paper Trading!")
print("   Initial Cash: $100,000")
print("   Slippage: 1 basis point")
PYTHON
    ;;

  2)
    echo "🔄 Switching to Tiger Brokers..."
    read -p "Enter Tiger Account ID: " account_id
    read -p "Enter path to private key: " key_path
    
    # Update config
    python3 << PYTHON
import yaml

with open('config/finance.yaml', 'r') as f:
    config = yaml.safe_load(f)

config['execution']['broker'] = 'tiger'
config['execution']['broker_config'] = {
    'tiger': {
        'account_id': '$account_id',
        'private_key_path': '$key_path',
        'server': 'https://api.tigerbrokers.com'
    }
}

with open('config/finance.yaml', 'w') as f:
    yaml.dump(config, f, default_flow_style=False, sort_keys=False)

print("✅ Switched to Tiger Brokers!")
print("   Account ID: $account_id")
print("   Key Path: $key_path")
PYTHON

    # Update/create .env
    echo ""
    echo "Updating .env file..."
    if [ -f "$ENV_FILE" ]; then
        # Update existing
        sed -i "s/TIGER_ACCOUNT_ID=.*/TIGER_ACCOUNT_ID=$account_id/" "$ENV_FILE" 2>/dev/null || echo "TIGER_ACCOUNT_ID=$account_id" >> "$ENV_FILE"
        sed -i "s|TIGER_PRIVATE_KEY_PATH=.*|TIGER_PRIVATE_KEY_PATH=$key_path|" "$ENV_FILE" 2>/dev/null || echo "TIGER_PRIVATE_KEY_PATH=$key_path" >> "$ENV_FILE"
    else
        # Create new
        cat > "$ENV_FILE" << ENVFILE
TIGER_ACCOUNT_ID=$account_id
TIGER_PRIVATE_KEY_PATH=$key_path
TIGER_SERVER=https://api.tigerbrokers.com
ENVFILE
    fi
    echo "✅ .env file updated"
    ;;

  3)
    echo ""
    echo "📋 Broker Configuration:"
    echo "================================================"
    grep -A 20 "^execution:" "$CONFIG_FILE"
    echo "================================================"
    ;;

  4)
    echo ""
    echo "🧪 Testing Broker Connection..."
    python3 << 'PYTHON'
import sys
sys.path.insert(0, '/home/claw.zhao/.openclaw/workspace/AITradeAgent')

from finance_service.brokers.factory import BrokerFactory

try:
    # Test Paper
    print("Testing Paper Broker...")
    paper = BrokerFactory.create('paper', {'initial_cash': 50000})
    print("✅ Paper Broker: OK")
except Exception as e:
    print(f"❌ Paper Broker: {e}")

try:
    # Test Tiger (requires .env)
    print("\nTesting Tiger Broker...")
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    config = {
        'account_id': os.getenv('TIGER_ACCOUNT_ID'),
        'private_key_path': os.getenv('TIGER_PRIVATE_KEY_PATH'),
        'server': os.getenv('TIGER_SERVER', 'https://api.tigerbrokers.com')
    }
    
    if config['account_id']:
        tiger = BrokerFactory.create('tiger', config)
        print("✅ Tiger Broker: OK (config loaded)")
    else:
        print("⚠️  Tiger Broker: Credentials not configured in .env")
except Exception as e:
    print(f"❌ Tiger Broker: {e}")
PYTHON
    ;;

  0)
    echo "Exiting..."
    exit 0
    ;;

  *)
    echo "Invalid choice!"
    ;;
esac

echo ""
echo "💡 Next step: Restart the service for changes to take effect"
echo "   pkill -f 'run_finance_service.py'"
echo "   python3 run_finance_service.py &"
