#!/bin/bash
# ============================================================
#  Quantom Bot — Oracle Cloud ARM64 Setup Script
#  Run once on a fresh Ubuntu 22.04 instance:
#    curl -fsSL https://raw.githubusercontent.com/YOUR/REPO/main/deploy/oracle-setup.sh | bash
# ============================================================
set -e

echo "🚀 Installing Docker..."
apt-get update -qq
apt-get install -y -qq curl git ca-certificates gnupg lsb-release

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update -qq
apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

systemctl enable docker
systemctl start docker

echo "✅ Docker installed"

echo "🔥 Opening firewall ports..."
iptables -I INPUT -p tcp --dport 5000 -j ACCEPT
iptables -I INPUT -p tcp --dport 80 -j ACCEPT
iptables -I INPUT -p tcp --dport 443 -j ACCEPT
apt-get install -y -qq iptables-persistent
netfilter-persistent save

echo "✅ Firewall configured"

echo "📁 Creating /opt/quantom directory..."
mkdir -p /opt/quantom
echo ""
echo "============================================================"
echo "  ✅ Oracle Cloud setup complete!"
echo ""
echo "  Next steps:"
echo "  1. Upload your project:  scp -r ./quantom-v2 ubuntu@YOUR_IP:/opt/quantom/"
echo "  2. Copy env file:        cp deploy/.env.example deploy/.env  then fill values"
echo "  3. Launch:               cd /opt/quantom/deploy && docker compose up -d"
echo "============================================================"
