"""
Supabase client — works alongside Neon/PostgreSQL (QUANTOM_DB_URL).
Gives the bot full freedom to read/write Supabase storage, realtime, and DB.

Required env vars:
  SUPABASE_URL          — https://xxxx.supabase.co
  SUPABASE_ANON_KEY     — sb_publishable_...
  SUPABASE_SERVICE_KEY  — sb_secret_...
"""

import os
from dotenv import load_dotenv

load_dotenv(override=True)

SUPABASE_URL: str = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY: str = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_KEY: str = os.environ.get("SUPABASE_SERVICE_KEY", "")

_client = None
_admin_client = None


def get_supabase():
    """Public client — uses anon key (safe for mobile/frontend calls)."""
    global _client
    if _client is None:
        if not SUPABASE_URL or not SUPABASE_ANON_KEY:
            return None
        try:
            from supabase import create_client
            _client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
        except Exception as e:
            print(f"[Supabase] ⚠️  Could not init client: {e}")
            return None
    return _client


def get_supabase_admin():
    """Admin client — uses service key (full access, backend only)."""
    global _admin_client
    if _admin_client is None:
        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
            return None
        try:
            from supabase import create_client
            _admin_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        except Exception as e:
            print(f"[Supabase] ⚠️  Could not init admin client: {e}")
            return None
    return _admin_client


def is_configured() -> bool:
    return bool(SUPABASE_URL and (SUPABASE_ANON_KEY or SUPABASE_SERVICE_KEY))


async def supabase_query(table: str, query_type: str = "select", filters: dict = None, data: dict = None, limit: int = 100):
    """
    Generic Supabase query helper — the bot can call this freely.
    query_type: select | insert | update | delete | upsert
    """
    sb = get_supabase_admin() or get_supabase()
    if not sb:
        return {"ok": False, "error": "Supabase not configured — add SUPABASE_URL to secrets"}

    try:
        ref = sb.table(table)
        if query_type == "select":
            q = ref.select("*")
            if filters:
                for k, v in filters.items():
                    q = q.eq(k, v)
            q = q.limit(limit)
            res = q.execute()
        elif query_type == "insert":
            res = ref.insert(data or {}).execute()
        elif query_type == "upsert":
            res = ref.upsert(data or {}).execute()
        elif query_type == "update":
            q = ref.update(data or {})
            if filters:
                for k, v in filters.items():
                    q = q.eq(k, v)
            res = q.execute()
        elif query_type == "delete":
            q = ref.delete()
            if filters:
                for k, v in filters.items():
                    q = q.eq(k, v)
            res = q.execute()
        else:
            return {"ok": False, "error": f"Unknown query_type: {query_type}"}

        return {"ok": True, "data": res.data, "count": len(res.data) if res.data else 0}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def supabase_storage_upload(bucket: str, path: str, content: bytes, content_type: str = "application/octet-stream"):
    """Upload a file to Supabase Storage."""
    sb = get_supabase_admin()
    if not sb:
        return {"ok": False, "error": "Supabase not configured"}
    try:
        res = sb.storage.from_(bucket).upload(path, content, {"content-type": content_type, "upsert": "true"})
        url = sb.storage.from_(bucket).get_public_url(path)
        return {"ok": True, "path": path, "url": url}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def supabase_storage_list(bucket: str, folder: str = ""):
    """List files in a Supabase Storage bucket."""
    sb = get_supabase_admin()
    if not sb:
        return {"ok": False, "error": "Supabase not configured"}
    try:
        res = sb.storage.from_(bucket).list(folder)
        return {"ok": True, "files": res}
    except Exception as e:
        return {"ok": False, "error": str(e)}
