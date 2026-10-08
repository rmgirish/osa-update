#!/bin/bash
set -e

echo "=========================================="
echo " Starting EC2 Instance Provisioning & Setup"
echo "=========================================="

# 1. Update package manager
echo "[1/4] Updating packages..."
sudo apt-get update -y
sudo apt-get upgrade -y
sudo apt-get install -y curl git ufw fail2ban ca-certificates gnupg lsb-release

# 2. Configure 4GB Swap Space (essential for smaller EC2 instances like t2.micro / t3.small)
if ! grep -q '/swapfile' /proc/swaps; then
    echo "[2/4] Allocating 4GB swap space to prevent Out-Of-Memory issues..."
    sudo fallocate -l 4G /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1M count=4096
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    echo "vm.swappiness=10" | sudo tee -a /etc/sysctl.conf
    sudo sysctl -p
    echo "Swap space created and enabled."
else
    echo "[2/4] Swap space already exists, skipping."
fi

# 3. Install Docker Engine and Docker Compose Plugin
echo "[3/4] Installing Docker and Docker Compose..."
if ! command -v docker &> /dev/null; then
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg

    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

    sudo apt-get update -y
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    # Enable and start Docker service
    sudo systemctl enable docker
    sudo systemctl start docker

    # Add current user to docker group
    sudo usermod -aG docker "$USER"
    echo "Docker installed successfully."
else
    echo "Docker is already installed."
fi

# 4. Configure basic UFW firewall
echo "[4/4] Configuring firewall..."
sudo ufw allow 22/tcp comment 'SSH'
sudo ufw allow 80/tcp comment 'HTTP'
sudo ufw allow 443/tcp comment 'HTTPS'
sudo ufw --force enable

echo "=========================================="
echo " Setup complete!"
echo " IMPORTANT: Run 'newgrp docker' or reconnect SSH"
echo " for docker group permissions to take effect."
echo "=========================================="
