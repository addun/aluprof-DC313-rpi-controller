#!/bin/bash

# Aluprof DC313 RPi Controller - Uninstallation Script
# This script removes the systemd service

set -e  # Exit on any error

SERVICE_NAME="aluprof-dc313-rpi-controller"

echo "🛑 Uninstalling Aluprof DC313 RPi Controller service..."

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   echo "❌ This script should not be run as root. Please run as the pi user."
   exit 1
fi

# Stop the service if it's running
echo "⏹️  Stopping service..."
sudo systemctl stop "$SERVICE_NAME" || echo "Service was not running"

# Disable the service
echo "❌ Disabling service..."
sudo systemctl disable "$SERVICE_NAME" || echo "Service was not enabled"

# Remove the symlink
echo "🗑️  Removing service file..."
sudo rm -f "/etc/systemd/system/${SERVICE_NAME}.service"

# Reload systemd daemon
echo "🔄 Reloading systemd daemon..."
sudo systemctl daemon-reload

# Reset failed services
sudo systemctl reset-failed

echo ""
echo "✅ Uninstallation complete!"
echo "The Aluprof DC313 RPi Controller service has been removed and will no longer start on boot."
echo ""
echo "Note: The virtual environment (venv/) directory can be manually deleted if no longer needed."