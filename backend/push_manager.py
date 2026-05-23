"""
PushManager — Expo Push Notifications (مجاني، بدون خدمة خارجية)
يُرسل إشعارات للأجهزة المسجّلة عبر Expo Push API المجانية.
Tokens مُخزّنة في الذاكرة + ملف JSON محلي.
"""

import json
import os
from typing import Optional

import httpx

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
TOKENS_FILE = os.path.join(os.path.dirname(__file__), ".push_tokens.json")


class PushManager:
    _instance: Optional["PushManager"] = None

    @classmethod
    def get_instance(cls) -> "PushManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        self._tokens: set[str] = set()
        self._load_tokens()
        print(f"[Push] Ready — {len(self._tokens)} device(s) registered")

    def _load_tokens(self) -> None:
        try:
            if os.path.exists(TOKENS_FILE):
                data = json.loads(open(TOKENS_FILE).read())
                self._tokens = set(data.get("tokens", []))
        except Exception as e:
            print(f"[Push] Could not load tokens: {e}")

    def _save_tokens(self) -> None:
        try:
            with open(TOKENS_FILE, "w") as f:
                json.dump({"tokens": list(self._tokens)}, f)
        except Exception as e:
            print(f"[Push] Could not save tokens: {e}")

    def register(self, token: str) -> bool:
        token = token.strip()
        if not token:
            return False
        # Expo tokens look like: ExponentPushToken[xxx] or ExpoPushToken[xxx]
        if not (token.startswith("ExponentPushToken[") or token.startswith("ExpoPushToken[")):
            return False
        added = token not in self._tokens
        self._tokens.add(token)
        if added:
            self._save_tokens()
            print(f"[Push] New device registered — total: {len(self._tokens)}")
        return True

    def unregister(self, token: str) -> None:
        self._tokens.discard(token)
        self._save_tokens()

    @property
    def token_count(self) -> int:
        return len(self._tokens)

    async def send(
        self,
        title: str,
        body: str,
        data: dict | None = None,
        sound: str = "default",
        badge: int | None = None,
    ) -> dict:
        """إرسال إشعار لجميع الأجهزة المسجّلة."""
        if not self._tokens:
            return {"sent": 0, "note": "no devices registered"}

        messages = []
        for token in self._tokens:
            msg: dict = {
                "to": token,
                "title": title,
                "body": body,
                "sound": sound,
                "priority": "high",
                "data": data or {},
            }
            if badge is not None:
                msg["badge"] = badge
            messages.append(msg)

        results: dict = {"sent": 0, "failed": 0, "errors": []}
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                # Expo accepts a single object or an array
                payload = messages if len(messages) > 1 else messages[0]
                resp = await client.post(
                    EXPO_PUSH_URL,
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                )
                if resp.status_code == 200:
                    results["sent"] = len(messages)
                    print(f"[Push] ✅ Sent '{title}' → {len(messages)} device(s)")
                else:
                    results["failed"] = len(messages)
                    results["errors"].append(f"HTTP {resp.status_code}: {resp.text[:120]}")
                    print(f"[Push] ❌ Failed: {resp.status_code}")
        except Exception as e:
            results["failed"] = len(messages)
            results["errors"].append(str(e)[:120])
            print(f"[Push] ❌ Error: {e}")

        return results
