"""
hf_client.py — HuggingFace External Connectivity
البوت يتصل بخوادم خارجية عبر HuggingFace API:
  • Inference API  → تشغيل نماذج AI على HuggingFace مجاناً
  • Space API      → استدعاء أي Space عام على HuggingFace
  • Web Fetch      → جلب بيانات من أي URL خارجي
"""
from __future__ import annotations
import asyncio
import json
import os
from typing import Any

import httpx

# ── Token resolution (DB → env → HF_TOKEN) ────────────────────────────────────

_cached_token: str | None = None

async def get_hf_token(db=None) -> str | None:
    global _cached_token
    if _cached_token:
        return _cached_token

    # 1. From DB ai_keys table
    if db is not None:
        try:
            rows = await db.get_ai_keys("huggingface")
            if rows:
                _cached_token = rows[0].get("api_key", "").strip()
                if _cached_token:
                    return _cached_token
        except Exception:
            pass

    # 2. From environment
    env_tok = os.environ.get("HF_TOKEN", "").strip()
    if env_tok:
        _cached_token = env_tok
        return _cached_token

    return None


def invalidate_token_cache():
    global _cached_token
    _cached_token = None


# ── HuggingFace Inference API ─────────────────────────────────────────────────

HF_INFERENCE_BASE = "https://api-inference.huggingface.co/models"

RECOMMENDED_MODELS = {
    "sentiment":     "cardiffnlp/twitter-roberta-base-sentiment-latest",
    "summarize":     "facebook/bart-large-cnn",
    "translate_ar":  "Helsinki-NLP/opus-mt-en-ar",
    "translate_en":  "Helsinki-NLP/opus-mt-ar-en",
    "classify":      "facebook/bart-large-mnli",
    "fill_mask":     "bert-base-multilingual-cased",
    "question":      "deepset/roberta-base-squad2",
    "generate":      "mistralai/Mistral-7B-Instruct-v0.3",
    "crypto_news":   "ProsusAI/finbert",
}


async def hf_inference(
    model_or_task: str,
    inputs: str | dict,
    parameters: dict | None = None,
    db=None,
    timeout: int = 30,
) -> dict[str, Any]:
    """
    يستدعي HuggingFace Inference API لتشغيل نموذج AI.
    model_or_task: اسم النموذج الكامل أو مهمة (sentiment, summarize, ...)
    inputs: النص أو البيانات المدخلة
    """
    token = await get_hf_token(db)

    # Resolve shorthand task names
    model = RECOMMENDED_MODELS.get(model_or_task.lower(), model_or_task)
    url   = f"{HF_INFERENCE_BASE}/{model}"

    payload: dict[str, Any] = {
        "inputs": inputs,
    }
    if parameters:
        payload["parameters"] = parameters

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(url, json=payload, headers=headers)
            if r.status_code == 503:
                return {
                    "ok": False,
                    "error": "النموذج يحمّل (loading) — حاول مرة أخرى بعد 20 ثانية",
                    "model": model,
                    "retry_after": 20,
                }
            if r.status_code == 401:
                return {
                    "ok": False,
                    "error": "توكن HuggingFace غير صحيح أو مفقود — أضفه في الإعدادات",
                    "model": model,
                }
            data = r.json()
            return {"ok": True, "model": model, "result": data, "status": r.status_code}
    except httpx.TimeoutException:
        return {"ok": False, "error": f"انتهت مهلة الاتصال بـ {model}", "model": model}
    except Exception as e:
        return {"ok": False, "error": str(e), "model": model}


# ── HuggingFace Space API ──────────────────────────────────────────────────────

async def hf_space_call(
    space_id: str,
    api_name: str = "/predict",
    data: list | None = None,
    db=None,
    timeout: int = 30,
) -> dict[str, Any]:
    """
    يستدعي Space API على HuggingFace.
    space_id: مثال "mstuv23/quantom-v2" أو رابط كامل
    api_name: اسم الـ endpoint مثل /predict أو /run/predict
    data: البيانات المرسلة كـ list
    """
    token = await get_hf_token(db)

    # Build URL
    space_id = space_id.replace("https://huggingface.co/spaces/", "").strip("/")
    owner, name = (space_id.split("/") + [""])[:2]
    # HF Spaces expose API at: https://owner-name.hf.space/run/predict
    hf_name = name.replace("_", "-").lower()
    owner_clean = owner.replace("_", "-").lower()
    base_url = f"https://{owner_clean}-{hf_name}.hf.space"
    url = f"{base_url}{api_name}"

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    payload = {"data": data or []}

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(url, json=payload, headers=headers)
            return {
                "ok": r.status_code == 200,
                "space": space_id,
                "url": url,
                "status": r.status_code,
                "result": r.json() if "application/json" in r.headers.get("content-type", "") else r.text,
            }
    except httpx.TimeoutException:
        return {"ok": False, "error": f"انتهت مهلة الاتصال بـ Space {space_id}", "url": url}
    except Exception as e:
        return {"ok": False, "error": str(e), "space": space_id}


# ── Generic Web Fetch ──────────────────────────────────────────────────────────

async def web_fetch(
    url: str,
    method: str = "GET",
    headers: dict | None = None,
    body: dict | None = None,
    timeout: int = 15,
) -> dict[str, Any]:
    """
    يجلب بيانات من أي URL خارجي (مجاني، لا يحتاج توكن).
    مفيد لأسعار العملات، أخبار السوق، بيانات API العامة.
    """
    hdrs = {
        "User-Agent": "Quantom-Bot/2.0 (+https://huggingface.co/spaces/mstuv23/quantom-v2)",
        "Accept": "application/json, text/plain, */*",
    }
    if headers:
        hdrs.update(headers)

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            if method.upper() == "GET":
                r = await client.get(url, headers=hdrs)
            else:
                r = await client.post(url, json=body or {}, headers=hdrs)

            ct = r.headers.get("content-type", "")
            if "application/json" in ct:
                content = r.json()
            else:
                content = r.text[:4000]  # Limit text response

            return {
                "ok": r.status_code < 400,
                "url": url,
                "status": r.status_code,
                "content": content,
            }
    except httpx.TimeoutException:
        return {"ok": False, "error": f"انتهت مهلة الاتصال بـ {url}"}
    except Exception as e:
        return {"ok": False, "error": str(e), "url": url}


# ── Connection Test ────────────────────────────────────────────────────────────

async def test_hf_connection(db=None) -> dict[str, Any]:
    """يختبر الاتصال بـ HuggingFace ويُعيد حالة التوكن."""
    token = await get_hf_token(db)
    if not token:
        return {
            "ok": False,
            "connected": False,
            "message": "لا يوجد توكن HuggingFace — أضفه في الإعدادات",
            "token_set": False,
        }

    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get("https://huggingface.co/api/whoami-v2", headers=headers)
            if r.status_code == 200:
                info = r.json()
                return {
                    "ok": True,
                    "connected": True,
                    "username": info.get("name", "unknown"),
                    "token_set": True,
                    "message": f"✅ متصل بـ HuggingFace كـ @{info.get('name', 'unknown')}",
                    "plan": info.get("type", "free"),
                }
            else:
                return {
                    "ok": False,
                    "connected": False,
                    "token_set": True,
                    "message": "❌ التوكن غير صحيح أو منتهي الصلاحية",
                }
    except Exception as e:
        return {"ok": False, "connected": False, "error": str(e), "token_set": bool(token)}


# ── Quick helpers for common tasks ─────────────────────────────────────────────

async def analyze_sentiment(text: str, db=None) -> str:
    """تحليل مشاعر النص (إيجابي/سلبي/محايد)."""
    result = await hf_inference("sentiment", text, db=db)
    if not result["ok"]:
        return result.get("error", "فشل التحليل")
    data = result.get("result", [])
    if isinstance(data, list) and data:
        top = max(data[0] if isinstance(data[0], list) else data,
                  key=lambda x: x.get("score", 0) if isinstance(x, dict) else 0)
        label = top.get("label", "").upper() if isinstance(top, dict) else str(top)
        score = top.get("score", 0) if isinstance(top, dict) else 0
        label_ar = {"POSITIVE": "إيجابي ✅", "NEGATIVE": "سلبي ❌", "NEUTRAL": "محايد ⚖️",
                    "LABEL_2": "إيجابي ✅", "LABEL_1": "محايد ⚖️", "LABEL_0": "سلبي ❌"}.get(label, label)
        return f"{label_ar} ({score*100:.1f}%)"
    return str(data)


async def fetch_crypto_price(symbol: str = "bitcoin") -> dict:
    """يجلب سعر عملة من CoinGecko (مجاني بلا مفتاح)."""
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={symbol.lower()}&vs_currencies=usd&include_24hr_change=true"
    return await web_fetch(url)


async def fetch_crypto_news(query: str = "crypto bitcoin") -> dict:
    """يجلب أخبار عملات رقمية من NewsAPI البديل المجاني."""
    url = f"https://cryptopanic.com/api/v1/posts/?auth_token=free&filter=hot&currencies=BTC,ETH"
    return await web_fetch(url)
