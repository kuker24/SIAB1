#!/bin/bash
# =============================================================================
# SSH Key Setup Script
# Run this ONCE to setup passwordless SSH access
# =============================================================================

echo "🔐 Setting up SSH Key for passwordless access..."
echo ""

SSH_PORT=2222
SSH_USER="fahmi"
SSH_HOST="127.0.0.1"
KEY_PATH="$HOME/.ssh/id_rsa_ujian"

# Check if key already exists
if [ -f "${KEY_PATH}" ]; then
    echo "✓ SSH key already exists at ${KEY_PATH}"
    echo ""
    read -p "Do you want to use existing key? (y/n): " use_existing
    
    if [ "$use_existing" != "y" ]; then
        echo "Generating new key..."
        ssh-keygen -t rsa -b 4096 -f "${KEY_PATH}" -N "" -C "ujian_sync_key"
    fi
else
    echo "📝 Generating new SSH key..."
    echo ""
    ssh-keygen -t rsa -b 4096 -f "${KEY_PATH}" -N "" -C "ujian_sync_key"
fi

echo ""
echo "📤 Copying key to server..."
echo "Please enter your SSH password ONE LAST TIME:"
echo ""

# Copy key to server
cat "${KEY_PATH}.pub" | ssh -p ${SSH_PORT} ${SSH_USER}@${SSH_HOST} \
    "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ SSH key setup complete!"
    echo ""
    echo "🎉 From now on, you can sync WITHOUT password!"
    echo ""
    echo "Next steps:"
    echo "  1. Run: ./sync-nopass.sh"
    echo "  2. Enjoy passwordless sync!"
    echo ""
else
    echo ""
    echo "❌ Failed to copy key to server."
    echo "Please check your password and try again."
    exit 1
fi
