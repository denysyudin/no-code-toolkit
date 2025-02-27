#!/bin/bash

# Script to disable cloud dependencies and set up local storage
# Usage: ./disable-cloud.sh [storage_path] [base_url]

set -e
echo "===== No-Code Architects Toolkit: VPS Migration Tool ====="
echo "This script will configure your environment for local storage without cloud dependencies."

# Default values
STORAGE_PATH=${1:-"/var/www/storage"}
BASE_URL=${2:-"http://localhost:5000"}

# Make sure the API key is set
if [ -z "$API_KEY" ]; then
    echo "ERROR: API_KEY environment variable is not set."
    echo "Please set your API_KEY first:"
    echo "export API_KEY=your_generated_api_key"
    exit 1
fi

echo "Setting up local storage configuration..."
echo "Storage path: $STORAGE_PATH"
echo "Base URL: $BASE_URL"

# Create storage directory if it doesn't exist
if [ ! -d "$STORAGE_PATH" ]; then
    echo "Creating storage directory: $STORAGE_PATH"
    mkdir -p "$STORAGE_PATH"
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to create storage directory."
        echo "Try running with sudo or check permissions."
        exit 1
    fi
fi

# Set directory permissions
chmod 755 "$STORAGE_PATH"
if [ $? -ne 0 ]; then
    echo "WARNING: Failed to set permissions on storage directory."
    echo "Make sure the application has write access to this directory."
fi

# Export environment variables
export LOCAL_STORAGE_PATH="$STORAGE_PATH"
export BASE_URL="$BASE_URL"
export TEMP_STORAGE_PATH="/tmp"

# Save environment variables to .env file for future use
echo "Saving environment variables to .env file..."
cat > .env << EOF
# No-Code Architects Toolkit - Local VPS Configuration
API_KEY=$API_KEY
LOCAL_STORAGE_PATH=$STORAGE_PATH
BASE_URL=$BASE_URL
TEMP_STORAGE_PATH=/tmp
EOF

echo "Setting up environment variables for the current session..."
echo "export API_KEY=\"$API_KEY\"" >> ~/.bashrc
echo "export LOCAL_STORAGE_PATH=\"$STORAGE_PATH\"" >> ~/.bashrc
echo "export BASE_URL=\"$BASE_URL\"" >> ~/.bashrc
echo "export TEMP_STORAGE_PATH=\"/tmp\"" >> ~/.bashrc

echo "========================================================"
echo "Configuration complete!"
echo "To make these changes permanent, run:"
echo "source ~/.bashrc"
echo ""
echo "To start the application, run:"
echo "gunicorn app:create_app() --bind 0.0.0.0:5000"
echo "========================================================" 