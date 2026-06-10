#!/bin/bash
# Quantom V2 — Deploy Helper
# Usage: bash deploy.sh [fly|docker|oracle|alibaba]

set -e

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}╔══════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     Quantom V2 — Deploy Helper       ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════╝${NC}"

MODE=${1:-"docker"}

case $MODE in

  # ── Fly.io (مجاني 24/7) ───────────────────────────────────────
  fly)
    echo -e "\n${GREEN}▶ نشر على Fly.io (مجاني)...${NC}"
    if ! command -v flyctl &> /dev/null; then
      echo -e "${YELLOW}تثبيت flyctl...${NC}"
      curl -L https://fly.io/install.sh | sh
      export PATH="$HOME/.fly/bin:$PATH"
    fi
    echo -e "${YELLOW}تسجيل الدخول (سيفتح المتصفح)...${NC}"
    flyctl auth login
    echo -e "${YELLOW}إضافة متغيرات البيئة السرية...${NC}"
    read -p "أدخل QUANTOM_DB_URL: " DB_URL
    flyctl secrets set QUANTOM_DB_URL="$DB_URL"
    echo -e "${GREEN}رفع التطبيق...${NC}"
    flyctl deploy
    echo -e "${GREEN}✅ تم! رابطك: https://quantom-v2.fly.dev${NC}"
    ;;

  # ── Docker على أي VPS (Alibaba / Oracle / DigitalOcean) ────────
  docker)
    echo -e "\n${GREEN}▶ تشغيل بـ Docker Compose...${NC}"
    if ! command -v docker &> /dev/null; then
      echo -e "${YELLOW}تثبيت Docker...${NC}"
      curl -fsSL https://get.docker.com | sh
      sudo usermod -aG docker $USER
    fi
    echo -e "${YELLOW}بناء وتشغيل الحاوية...${NC}"
    docker compose up -d --build
    echo -e "${GREEN}✅ يعمل على: http://$(hostname -I | awk '{print $1}'):5000/trade/health${NC}"
    docker compose logs -f --tail=20
    ;;

  # ── Oracle Cloud Always Free Setup ────────────────────────────
  oracle)
    echo -e "\n${GREEN}▶ إعداد Oracle Cloud Always Free...${NC}"
    echo -e "${YELLOW}الخطوات:${NC}"
    echo "1. سجّل على cloud.oracle.com (مجاني للأبد)"
    echo "2. أنشئ VM: Always Free AMD — Ubuntu 22.04 — 1GB RAM"
    echo "3. افتح Port 5000 في Security List"
    echo "4. SSH للسيرفر ثم نفّذ:"
    echo ""
    echo -e "${BLUE}  git clone <repo-url>"
    echo "  cd quantom-v2"
    echo "  bash deploy.sh docker${NC}"
    ;;

  # ── Alibaba Cloud ECS Setup ────────────────────────────────────
  alibaba)
    echo -e "\n${GREEN}▶ إعداد Alibaba Cloud ECS...${NC}"
    echo -e "${YELLOW}الخطوات:${NC}"
    echo "1. سجّل على alibabacloud.com وفعّل الـ Free Trial ($90 credits)"
    echo "2. أنشئ ECS: ecs.t6-c1m1.large — Ubuntu 22.04 — 1 vCPU 1GB RAM"
    echo "3. Security Group: افتح Port 5000 و 22"
    echo "4. SSH للسيرفر ثم نفّذ:"
    echo ""
    echo -e "${BLUE}  git clone <repo-url>"
    echo "  cd quantom-v2"
    echo "  bash deploy.sh docker${NC}"
    echo ""
    echo -e "${YELLOW}ملاحظة: Credits تكفي ~6-12 شهراً${NC}"
    ;;

  *)
    echo -e "${RED}استخدام: bash deploy.sh [fly|docker|oracle|alibaba]${NC}"
    exit 1
    ;;
esac
