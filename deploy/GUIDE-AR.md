# 🚀 دليل النشر — Oracle Cloud + Cloudflare Tunnel

## الهدف
سيرفر Python يعمل **24/7 بدون توقف أبداً** مع URL ثابت سريع عبر Cloudflare.

---

## الخطوة 1 — إنشاء سيرفر Oracle Cloud (مجاني للأبد)

1. اذهب إلى [cloud.oracle.com](https://cloud.oracle.com) وسجّل حساباً
2. من القائمة: **Compute → Instances → Create Instance**
3. اختر الإعدادات التالية:
   - **Image**: Ubuntu 22.04
   - **Shape**: `VM.Standard.A1.Flex` (ARM — مجاني)
   - **OCPU**: 2 | **RAM**: 12 GB
4. أنشئ SSH Key وحمّل الـ Private Key
5. انتظر حتى تصبح الحالة **Running**
6. انسخ الـ **Public IP**

---

## الخطوة 2 — إعداد السيرفر (أمر واحد)

```bash
# اتصل بالسيرفر
ssh -i ~/your-key.pem ubuntu@YOUR_ORACLE_IP

# شغّل سكريبت الإعداد
curl -fsSL https://YOUR_RAW_SCRIPT_URL | sudo bash
```

أو يدوياً:
```bash
ssh -i ~/your-key.pem ubuntu@YOUR_ORACLE_IP
sudo apt update && sudo apt install -y docker.io docker-compose-v2 git
sudo usermod -aG docker ubuntu
```

---

## الخطوة 3 — إنشاء Cloudflare Tunnel (مجاني)

1. اذهب إلى [dash.cloudflare.com](https://dash.cloudflare.com)
2. من القائمة: **Zero Trust → Networks → Tunnels**
3. اضغط **Create a tunnel** → اختر **Cloudflared**
4. اكتب اسماً: `quantom-bot`
5. انسخ الـ **Tunnel Token** (سيبدو بـ `eyJhIjo...`)
6. في قسم **Public Hostname**:
   - Subdomain: `quantom-bot`
   - Domain: اختر دومينك أو استخدم cloudflare.com المجاني
   - Service: `http://quantom-bot:5000`
7. احفظ الـ URL مثل: `quantom-bot.yourdomain.com`

---

## الخطوة 4 — رفع المشروع وتشغيله

```bash
# من جهازك المحلي — ارفع الملفات
scp -r -i ~/your-key.pem /path/to/quantom-v2 ubuntu@YOUR_ORACLE_IP:/opt/quantom/

# اتصل بالسيرفر
ssh -i ~/your-key.pem ubuntu@YOUR_ORACLE_IP

# ادخل على مجلد النشر
cd /opt/quantom/deploy

# انسخ ملف الإعداد وعدّله
cp .env.example .env
nano .env
# أضف: QUANTOM_DB_URL, CLOUDFLARE_TUNNEL_TOKEN, SERVER_DOMAIN

# شغّل الكل
docker compose up -d --build
```

---

## الخطوة 5 — ربط التطبيق بالسيرفر الجديد

افتح التطبيق → Settings → Server Domain:
```
quantom-bot.yourdomain.com
```

---

## التحقق من عمل كل شيء

```bash
# تحقق من الحاويات
docker compose ps

# تحقق من الـ API
curl https://quantom-bot.yourdomain.com/trade/ping
# يجب أن يرد: {"status":"alive","ok":true}

# اقرأ اللوجز
docker compose logs -f quantom-bot
```

---

## المزايا التي تحصل عليها

| الميزة | التفاصيل |
|--------|----------|
| ⚡ سرعة | Cloudflare CDN في 200+ مدينة عالمياً |
| 🛡️ حماية | DDoS Protection تلقائي |
| 🔒 HTTPS | شهادة SSL مجانية تلقائية |
| 💤 لا توقف | السيرفر يعمل حتى لو أغلقت Replit |
| 🆓 مجاني | Oracle Always Free + Cloudflare Free |
| 🔄 إعادة تشغيل تلقائية | `restart: always` في docker-compose |

---

## استكشاف الأخطاء

```bash
# إذا لم يعمل التونل
docker compose logs cloudflared

# إذا لم يبدأ البوت
docker compose logs quantom-bot

# إعادة تشغيل كامل
docker compose restart

# تحديث الكود وإعادة البناء
git pull && docker compose up -d --build
