# Quantom V2 — Islamic Smart Trading Bot

بوت تداول إسلامي ذكي يعمل على Spot فقط (بلا رافعة مالية)، يتعلم من كل صفقة ويتذكر كل شيء.

## Run & Operate

- Backend FastAPI: runs via workflow "Backend: FastAPI Server" on port 5000
- Mobile Expo: runs via workflow "Mobile: Expo Dev Server" on port 18115
- Database: External Render PostgreSQL — configured via `QUANTOM_DB_URL` in `backend/.env`
- `pnpm run typecheck` — full TypeScript check

## Stack

- **Backend**: FastAPI (Python) + asyncpg + PostgreSQL (Render external)
- **Mobile**: Expo React Native (TypeScript)
- **AI**: Multi-provider pool (Gemini, OpenAI, Claude, Groq, Grok, Custom) — unlimited keys
- **DB**: PostgreSQL on Render — `agent_memory`, `bot_knowledge`, `ai_keys`, `conversations`, `trades`

## Where things live

- `backend/` — FastAPI server, all Python logic
- `backend/database.py` — DB schema, all CRUD functions
- `backend/ai_agent.py` — AI key pool, unlimited provider support, chat logic
- `backend/memory_engine.py` — Bot memory engine (learn from trades + conversations)
- `backend/agent_core.py` — TradingAgent with AgentMemory pattern scores
- `backend/main.py` — All API endpoints (prefix: `/trade`)
- `artifacts/mobile/` — Expo React Native app
- `artifacts/mobile/app/(tabs)/brain.tsx` — Memory & knowledge UI
- `artifacts/mobile/app/(tabs)/settings.tsx` — AI key management UI
- `artifacts/mobile/constants/api.ts` — `getApiBase()` returns `https://domain/trade`

## Architecture decisions

- All FastAPI routes live under `router = APIRouter(prefix="/trade")` — so URLs are `/trade/agent/memory/full` etc.
- `getApiBase()` in mobile already appends `/trade` — so mobile calls `${getApiBase()}/agent/memory/full` = `/trade/agent/memory/full` ✅
- AI keys: stored in DB (`ai_keys` table) + env vars. Unlimited per provider (no 10/5/5 cap).
- Memory: dual-table (`agent_memory` for lessons, `bot_knowledge` for persistent facts). Both searched by `memory_engine.py`.
- SSL for Render DB: `_USE_SSL_RENDER=True` in `backend/.env` — uses `ssl=ssl_ctx` with cert verification disabled.

## Product

- Halal spot-only trading bot (no leverage, no margin)
- Multi-AI provider support with unlimited manual key input
- Persistent bot memory: learns from every trade, conversation, and user instruction — never forgets
- Brain screen: full memory view with search, lessons, knowledge base, manual note addition
- Config screen: add unlimited API keys for any AI provider

## User preferences

- بوت إسلامي حلال — Spot فقط، لا رافعة مالية
- مفاتيح API بلا حدود (unlimited keys per provider)
- ذاكرة قوية ودائمة تتعلم من كل شيء
- هدف: تصدير APK في النهاية

## Gotchas

- Backend DB: use `QUANTOM_DB_URL` (not `DATABASE_URL`) for Render external URL
- Direct test FastAPI: `curl http://localhost:5000/trade/...` (NOT through localhost:80 proxy)
- Bot is halal: never suggest leverage, margin, or non-spot instruments
- `memory_engine.py` is imported lazily inside try/except in `ai_agent.py` — safe if missing

## Pointers

- See the `pnpm-workspace` skill for workspace structure
