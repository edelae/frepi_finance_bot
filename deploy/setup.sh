#!/bin/bash
# Frepi Finance Bot - GCP VM Setup Script
# Run this script on the existing frepi-agent VM

set -e

echo "=========================================="
echo "  Frepi Finance Bot - Setup"
echo "=========================================="

# Update system
echo "Updating system packages..."
sudo apt-get update

# Python should already be installed from frepi-agent setup
# Check for Python 3.11+
PYTHON=$(which python3.11 || which python3.10 || which python3)
echo "Using Python: $PYTHON ($($PYTHON --version))"

# Create app directory
echo "Creating app directory..."
sudo mkdir -p /opt/frepi-finance
sudo chown $USER:$USER /opt/frepi-finance

# Create virtual environment
echo "Creating virtual environment..."
$PYTHON -m venv /opt/frepi-finance/venv
source /opt/frepi-finance/venv/bin/activate

# Install dependencies
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install openai python-telegram-bot supabase httpx python-dotenv click rich apscheduler

# Copy application files
echo "Copying application files..."
cp -r frepi_finance /opt/frepi-finance/

# Create .env placeholder
echo "Creating .env placeholder..."
if [ ! -f /opt/frepi-finance/.env ]; then
    cat > /opt/frepi-finance/.env << 'EOF'
# Frepi Finance Bot Configuration
# Fill in your values below

OPENAI_API_KEY=your-openai-key-here
SUPABASE_URL=your-supabase-url-here
SUPABASE_KEY=your-supabase-key-here
TELEGRAM_FINANCE_BOT_TOKEN=your-telegram-token-here

CHAT_MODEL=gpt-4o
ENVIRONMENT=production
LOG_LEVEL=INFO
CMV_TARGET_PERCENT=32.0
SIGNIFICANT_PRICE_CHANGE_PERCENT=10.0
EOF
    echo "Please edit /opt/frepi-finance/.env with your credentials!"
fi

# Install systemd service
echo "Installing systemd service..."
sudo cp deploy/frepi-finance.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable frepi-finance

echo ""
echo "=========================================="
echo "  Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Edit /opt/frepi-finance/.env with your credentials"
echo "2. Start the service: sudo systemctl start frepi-finance"
echo "3. Check status: sudo systemctl status frepi-finance"
echo "4. View logs: sudo journalctl -u frepi-finance -f"
echo ""
