"""
Quantom Meta Engine — صلاحيات مطلقة للبوت على كل البنية التحتية.
File I/O · SQL · Shell commands · Project map
"""
import asyncio
import os
import re
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path("/home/runner/workspace")

# ── Path security ─────────────────────────────────────────────────────────────

def _resolve(path: str) -> Path:
    path = path.strip().lstrip("/")
    resolved = (PROJECT_ROOT / path).resolve()
    if not str(resolved).startswith(str(PROJECT_ROOT)):
        raise ValueError(f"Path outside project: {path}")
    return resolved


# ── File operations ───────────────────────────────────────────────────────────

def read_file(path: str) -> str:
    try:
        p = _resolve(path)
        if not p.exists():
            return f"❌ الملف غير موجود: {path}"
        size = p.stat().st_size
        if size > 300_000:
            return f"❌ الملف كبير جداً ({size//1024}KB): {path}. اقرأ جزءاً منه."
        return p.read_text(encoding="utf-8")
    except Exception as e:
        return f"❌ خطأ في قراءة {path}: {e}"


def write_file(path: str, content: str) -> str:
    try:
        p = _resolve(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"✅ تم حفظ الملف: {path} ({len(content):,} حرف)"
    except Exception as e:
        return f"❌ خطأ في كتابة {path}: {e}"


def list_files(path: str) -> str:
    try:
        p = _resolve(path)
        if not p.exists():
            return f"❌ المسار غير موجود: {path}"
        if p.is_file():
            return f"📄 ملف: {path} ({p.stat().st_size//1024}KB)"
        items = []
        for item in sorted(p.iterdir()):
            if item.name in ("__pycache__", ".git", "node_modules", ".expo"):
                continue
            if item.is_dir():
                items.append(f"📁 {item.name}/")
            else:
                kb = item.stat().st_size // 1024
                items.append(f"📄 {item.name} ({kb}KB)")
        return f"📂 {path}:\n" + "\n".join(items) if items else f"📂 {path}: مجلد فارغ"
    except Exception as e:
        return f"❌ خطأ في قائمة {path}: {e}"


# ── Database operations ───────────────────────────────────────────────────────

async def exec_sql(query: str, db: Any) -> str:
    try:
        q = query.strip()
        upper = q.upper().lstrip()
        is_select = upper.startswith("SELECT") or upper.startswith("WITH")
        if is_select:
            rows = await db._exec(q)
            if not rows:
                return "✅ SQL نجح — لا صفوف."
            header = " | ".join(rows[0].keys())
            lines  = [header, "-" * len(header)]
            for r in rows[:30]:
                lines.append(" | ".join(str(v) for v in r.values()))
            suffix = f"\n... ({len(rows)} صف)" if len(rows) > 30 else ""
            return "✅ نتيجة SQL:\n```\n" + "\n".join(lines) + suffix + "\n```"
        else:
            ok = await db._exec_status(q)
            return "✅ SQL نُفِّذ بنجاح." if ok else "⚠️ SQL نُفِّذ (لا تأكيد)."
    except Exception as e:
        return f"❌ خطأ SQL: {e}"


# ── Shell commands ────────────────────────────────────────────────────────────

async def exec_shell(command: str, timeout: int = 25) -> str:
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(PROJECT_ROOT),
            env={**os.environ, "PATH": "/usr/bin:/bin:/usr/local/bin:" + os.environ.get("PATH", "")},
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            return f"⏱️ الأمر انتهت مهلته ({timeout}s) — يعمل في الخلفية."
        out = stdout.decode(errors="replace").strip()
        err = stderr.decode(errors="replace").strip()
        code = proc.returncode
        icon = "✅" if code == 0 else f"⚠️ (exit {code})"
        parts = [icon]
        if out:
            parts.append(f"```\n{out[:3000]}\n```")
        if err:
            parts.append(f"stderr:\n```\n{err[:800]}\n```")
        return "\n".join(parts) if len(parts) > 1 else f"{icon} (بدون مخرجات)"
    except Exception as e:
        return f"❌ خطأ Shell: {e}"


# ── Project map for AI context ────────────────────────────────────────────────

PROJECT_MAP = """## خريطة المشروع — Quantom V2:

backend/                          ← Python FastAPI
  main.py          (endpoints)    ← كل الـ API (/trade/*)
  ai_agent.py      (AI pool)      ← مزودو AI، brain_chat، _parse_command
  agent_core.py    (TradingAgent) ← AgentMemory، pattern scores
  database.py      (DB CRUD)      ← جميع وظائف قاعدة البيانات
  scheduler.py     (trading loop) ← حلقة التداول التلقائي
  memory_engine.py (memory)       ← الذاكرة والمعرفة
  risk_manager.py  (risk)         ← إدارة المخاطر
  exchange_router.py (exchanges)  ← اختيار البورصة
  bybit_client.py  (exchange API) ← عميل البورصة
  meta_engine.py   (THIS FILE)    ← محرك التحكم المطلق
  .env                            ← متغيرات البيئة

artifacts/mobile/                 ← React Native Expo
  app/(tabs)/
    _layout.tsx    ← Tab bar — ترتيب وأيقونات التبويبات
    index.tsx      ← Dashboard — الصفحة الرئيسية
    chat.tsx       ← AI Chat — المحادثة العامة
    brain.tsx      ← Brain — التحكم الكامل + المحادثة مع العقل
    trades.tsx     ← Trades — الصفقات
    agent.tsx      ← Analytics — الإحصاءات
    settings.tsx   ← Settings — الإعدادات ومفاتيح API
    learn.tsx      ← Learn — التعلم
    accounts.tsx   ← Accounts — الحسابات
    company.tsx    ← Company — شركة التداول
  components/      ← مكونات مشتركة
  constants/api.ts ← getApiBase() — رابط API
  hooks/useColors.ts ← ألوان الثيم
  app.config.ts    ← إعدادات Expo
"""


# ── Command parser ─────────────────────────────────────────────────────────────

def parse_all_commands(text: str) -> list[dict]:
    """
    Parse ALL commands from AI response text.

    Supported formats:
      [COMMAND: name=value]          ← trading/bot commands
      [META: read_file=path]         ← read file
      [META: list_files=path]        ← list directory
      [META: exec_sql=query]         ← run SQL
      [META: exec_shell=command]     ← run shell command
      [WRITE_FILE: path/to/file]
      ```
      ...content...
      ```
      [/WRITE_FILE]
    """
    results: list[dict] = []

    # COMMAND blocks
    for m in re.finditer(r"\[COMMAND:\s*(\w+)(?:=([^\]]*))?\]", text):
        cmd = m.group(1).strip().lower()
        val = m.group(2).strip() if m.group(2) else None
        entry: dict = {"type": "command", "command": cmd}
        if val:
            try:
                entry["threshold"] = int(val)
            except (ValueError, TypeError):
                entry["value"] = val
        results.append(entry)

    # META inline blocks
    for m in re.finditer(r"\[META:\s*(\w+)=([^\]]{1,4000})\]", text, re.DOTALL):
        op  = m.group(1).strip().lower()
        val = m.group(2).strip()
        results.append({"type": "meta", "operation": op, "value": val})

    # WRITE_FILE blocks (multi-line)
    for m in re.finditer(
        r"\[WRITE_FILE:\s*([^\]]+)\]\s*```[^\n]*\n(.*?)```\s*\[/WRITE_FILE\]",
        text, re.DOTALL
    ):
        path    = m.group(1).strip()
        content = m.group(2)
        results.append({"type": "meta", "operation": "write_file", "path": path, "content": content})

    return results
