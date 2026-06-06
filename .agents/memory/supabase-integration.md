---
name: Supabase Integration
description: Supabase client setup alongside Neon DB — credentials, endpoints, and mobile config
---

# Supabase Integration

## Setup
- Project: Quantom / `fnixiuzcdfxkpsurgoju.supabase.co`
- Credentials stored in: `backend/.env` (SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_KEY, SUPABASE_DB_URL)
- SUPABASE_URL also set as Replit env var

## Backend
- Client module: `backend/supabase_client.py` — `get_supabase()` (anon) and `get_supabase_admin()` (service key)
- API endpoints under `/trade/supabase/`:
  - GET  `/status` — connection check
  - POST `/query` — generic SELECT/INSERT/UPDATE/DELETE/UPSERT on any table
  - GET  `/tables` — list public tables
  - POST `/storage/upload` — upload file to Storage bucket
  - GET  `/storage/{bucket}` — list bucket files
  - POST `/configure` — set SUPABASE_URL at runtime (no restart needed)

## Mobile
- Constants: `artifacts/mobile/constants/supabase.ts`
- Settings screen: SupabasePanel added showing connection status + test buttons
- eas.json bakes EXPO_PUBLIC_SUPABASE_URL and EXPO_PUBLIC_SUPABASE_ANON_KEY into APK builds

**Why:** User wants Supabase as a second DB alongside Neon, giving the bot freedom to use it for extended storage, realtime, and file storage.
**How to apply:** Always use supabase_client.py for Supabase access, never direct DB connection strings in app code. The bot calls endpoints under /trade/supabase/ freely.
