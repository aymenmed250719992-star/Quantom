#!/bin/bash
# ═══════════════════════════════════════════════════════════
#  Islamic Trading Bot — APK Builder
#  Builds an APK that connects to the Render backend (always-on).
#
#  BEFORE RUNNING:
#  1. Deploy the backend to Render (push to GitHub → Render auto-deploys)
#  2. Set your Render URL in eas.json → build.production.env.EXPO_PUBLIC_DOMAIN
#     e.g. "my-bot.onrender.com"
#  3. Run: eas login  (if not logged in)
#  4. Run: bash build-apk.sh
#
#  For preview build (same Render backend):
#     bash build-apk.sh preview
# ═══════════════════════════════════════════════════════════

set -e
cd "$(dirname "$0")"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  Islamic Trading Bot — APK Builder       ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
echo ""

# Check EAS login
if ! eas whoami &>/dev/null; then
  echo -e "${RED}❌ غير مسجّل الدخول في Expo${NC}"
  echo -e "${YELLOW}▶ شغّل أولاً: eas login${NC}"
  exit 1
fi

EXPO_USER=$(eas whoami 2>/dev/null)
echo -e "${GREEN}✅ مسجّل الدخول كـ: $EXPO_USER${NC}"
echo ""

# Determine build profile — default to production (stable always-on backend)
PROFILE="${1:-production}"
echo -e "${BLUE}📋 Build profile: ${PROFILE}${NC}"

# Read the domain from eas.json for the chosen profile
DOMAIN=$(python3 -c "
import json, sys
with open('eas.json') as f: c = json.load(f)
domain = c.get('build', {}).get('$PROFILE', {}).get('env', {}).get('EXPO_PUBLIC_DOMAIN', '')
print(domain)
" 2>/dev/null)

if [ -z "$DOMAIN" ] || [ "$DOMAIN" = "YOUR_RENDER_APP.onrender.com" ]; then
  echo -e "${RED}❌ لم يُحدَّد EXPO_PUBLIC_DOMAIN في eas.json → build.${PROFILE}.env${NC}"
  echo -e "${YELLOW}▶ عدّل eas.json وضع دومين الـ Render backend المنشور${NC}"
  echo -e "${YELLOW}   مثال: \"my-bot.onrender.com\"${NC}"
  exit 1
fi

echo -e "${GREEN}🌐 Backend domain: ${DOMAIN}${NC}"
echo ""
echo -e "${YELLOW}🔨 بدء بناء الـ APK... (قد يستغرق 10-15 دقيقة)${NC}"
echo ""

# Build APK
eas build --platform android --profile "$PROFILE" --non-interactive

echo ""
echo -e "${GREEN}✅ تم بناء الـ APK بنجاح!${NC}"
echo -e "${BLUE}   Backend: https://${DOMAIN}${NC}"
