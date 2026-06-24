#!/bin/bash
# Install Docker in WSL (Ubuntu)
# Run this script: ./install-docker-wsl.sh

set -e

echo "========================================"
echo "Installing Docker in WSL Ubuntu"
echo "========================================"
echo ""

# Update package list
echo "📦 Updating package list..."
sudo apt-get update

# Install prerequisites
echo "📦 Installing prerequisites..."
sudo apt-get install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release

# Add Docker's official GPG key
echo "🔑 Adding Docker's GPG key..."
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Set up the repository
echo "📝 Setting up Docker repository..."
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker Engine
echo "🐳 Installing Docker Engine..."
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Start Docker service
echo "🚀 Starting Docker service..."
sudo service docker start

# Add user to docker group
echo "👤 Adding $USER to docker group..."
sudo usermod -aG docker $USER

echo ""
echo "========================================"
echo "✅ Docker installed successfully!"
echo "========================================"
echo ""
echo "⚠️  IMPORTANT: Run this command to apply group changes:"
echo "   newgrp docker"
echo ""
echo "Or logout and login again to WSL"
echo ""
echo "Then test Docker:"
echo "   docker --version"
echo "   docker run hello-world"
echo ""
echo "After that, you can:"
echo "1. Login to Docker Hub: docker login"
echo "2. Build and push: ./docker-build-push.sh"
echo ""
