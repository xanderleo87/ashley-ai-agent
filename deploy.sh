#!/bin/bash
# Ashley AI Agent - VPS Deployment Script
# Run this on your Hostinger VPS after uploading files

echo "========================================"
echo "  Ashley AI Agent - VPS Setup"
echo "========================================"

# Update system
apt update && apt upgrade -y

# Install Python 3.11+ and pip
apt install -y python3 python3-pip python3-venv

# Create virtual environment
cd /root/ashley-ai-agent
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set up systemd service (keeps Ashley running 24/7)
cp ashley.service /etc/systemd/system/ashley.service
systemctl daemon-reload
systemctl enable ashley
systemctl start ashley

echo ""
echo "========================================"
echo "  Ashley is now running 24/7!"
echo "========================================"
echo ""
echo "Useful commands:"
echo "  systemctl status ashley    - Check if running"
echo "  systemctl restart ashley   - Restart"
echo "  systemctl stop ashley      - Stop"
echo "  journalctl -u ashley -f    - View live logs"
echo ""
