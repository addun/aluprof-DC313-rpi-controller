#!/bin/bash

# aluprof-dc313-rpi-controller - Startup Script
# This script pulls the latest changes and starts the application

set -e  # Exit on any error

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

echo "$(date): Starting aluprof-dc313-rpi-controller..."

# Pull latest changes from repository
echo "$(date): Pulling latest changes from repository..."
git fetch origin
git reset --hard origin/main

# Re-apply path substitutions after git reset
echo "$(date): Updating paths in service file..."
sed -i "s|__APP_DIR__|$APP_DIR|g" "aluprof-dc313-rpi-controller.service"

# Install/update Python dependencies in case requirements.txt changed
echo "$(date): Installing/updating Python dependencies..."
./venv/bin/pip install -r requirements.txt

# Start the application
echo "$(date): Starting the application..."
exec ./venv/bin/python main.py