# نشر Quantom V2 على HuggingFace Spaces
## مجاني 100% — بلا بطاقة بنكية

---

## الخطوات (10 دقائق فقط)

### 1. إنشاء حساب
- اذهب إلى: https://huggingface.co/join
- سجّل بإيميل فقط — لا بطاقة مطلوبة

### 2. إنشاء Space جديد
- اضغط على صورتك → New Space
- الاسم: `quantom-v2`
- SDK: **Docker**
- Visibility: **Private** (مهم — لا تجعله عام)
- اضغط Create Space

### 3. رفع الملفات
في Space الجديد، ارفع هذه الملفات من مجلد `backend/`:
```
Dockerfile.huggingface  ← أعده اسمه Dockerfile قبل الرفع
requirements.hf.txt     ← أعده اسمه requirements.txt
startup.py
main.py
database.py
ai_agent.py
memory_engine.py
agent_core.py
scheduler.py
learning_engine.py
bot_skills.py
adaptive_strategy.py
backtester.py
backtester_advanced.py
bybit_client.py
confluence_engine.py
exchange_router.py
audit_trail.py
```

### 4. إضافة متغيرات البيئة (Secrets)
في Space → Settings → Variables and Secrets → New Secret:

| الاسم | القيمة |
|-------|--------|
| `QUANTOM_DB_URL` | رابط Render PostgreSQL |
| `EXCHANGE_MODE` | `demo` |
| `EXCHANGE_NAME` | `mexc` |
| `MIN_CONFIDENCE_SCORE` | `55` |
| `_USE_SSL_RENDER` | `True` |

### 5. تشغيل التطبيق
Space سيبني Docker تلقائياً ويشتغل على:
```
https://YOUR-USERNAME-quantom-v2.hf.space/trade/health
```

### 6. تحديث رابط API في التطبيق
في `artifacts/mobile/constants/api.ts` غيّر الرابط إلى رابط HuggingFace.

---

## ملاحظات مهمة
- HuggingFace Spaces المجانية **تنام** بعد ~15 دقيقة عدم استخدام
- **الحل:** استخدم cron-job.org (مجاني) لإرسال ping كل 10 دقائق:
  - اذهب إلى https://cron-job.org
  - أنشئ job يفتح: `https://YOUR-USERNAME-quantom-v2.hf.space/trade/health`
  - كل 10 دقائق
  - **النتيجة: يعمل 24/7 مجاناً بلا بطاقة**

---

## الذاكرة والتعلّم
- **قاعدة البيانات** (Render PostgreSQL): تعمل دائماً، كل التعلّم محفوظ فيها للأبد ✅
- **الهاتف**: يحفظ نسخة احتياطية من المحادثات والذاكرة محلياً ✅
- حتى لو HuggingFace نام مؤقتاً، كل البيانات موجودة في DB ✅
