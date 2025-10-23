#!/bin/bash

# Aluprof Display Controller - Installation Script
# This script sets up the application to run automatically on Raspberry Pi boot

set -e  # Exit on any error

echo "🚀 Installing Aluprof DC313 RPi Controller as a system service..."

# Get the current directory (where the script is located)
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="aluprof"
SERVICE_FILE="${SERVICE_NAME}.service"

echo "📁 Application directory: $APP_DIR"

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   echo "❌ This script should not be run as root. Please run as the pi user."
   exit 1
fi

# Check if git is available
if ! command -v git &> /dev/null; then
    echo "❌ Git is not installed. Please install git first:"
    echo "   sudo apt update && sudo apt install git"
    exit 1
fi

# Check if we're in a git repository
if ! git rev-parse --git-dir &> /dev/null; then
    echo "❌ This directory is not a git repository."
    echo "   Please clone the repository first:"
    echo "   git clone https://github.com/addun/aluprof-DC313-rpi-controller.git"
    exit 1
fi

echo "✅ Git is available and this is a git repository"

# Update the service file and startup script with the correct paths
echo "📝 Updating service file and startup script with correct paths..."
sed -i "s|__APP_DIR__|$APP_DIR|g" "$SERVICE_FILE"
sed -i "s|__APP_DIR__|$APP_DIR|g" "start.sh"

# Make startup script executable
echo "🔧 Making startup script executable..."
chmod +x start.sh

# Create virtual environment
echo "🐍 Creating virtual environment..."
python3 -m venv venv

# Install Python dependencies in virtual environment
echo "📦 Installing Python dependencies in virtual environment..."
./venv/bin/pip install -r requirements.txt

# Create symlink to service file in systemd directory (requires sudo)
echo "🔧 Installing systemd service..."
sudo ln -sf "$APP_DIR/$SERVICE_FILE" "/etc/systemd/system/"

# Reload systemd daemon
echo "🔄 Reloading systemd daemon..."
sudo systemctl daemon-reload

# Enable the service to start on boot
echo "✅ Enabling service to start on boot..."
sudo systemctl enable "$SERVICE_NAME"

# Start the service now
echo "🚀 Starting the service..."
sudo systemctl start "$SERVICE_NAME"

# Check service status
echo "📊 Service status:"
sudo systemctl status "$SERVICE_NAME" --no-pager -l

echo ""
echo "🎉 Installation complete!"
echo ""
echo "Useful commands:"
echo "  Check status:    sudo systemctl status $SERVICE_NAME"
echo "  Start service:   sudo systemctl start $SERVICE_NAME"
echo "  Stop service:    sudo systemctl stop $SERVICE_NAME"
echo "  Restart service: sudo systemctl restart $SERVICE_NAME"
echo "  View logs:       sudo journalctl -u $SERVICE_NAME -f"
echo "  Disable service: sudo systemctl disable $SERVICE_NAME"
echo ""
echo "The app should now be running on http://localhost:4000"
echo "You can access it from other devices on your network using the Pi's IP address."