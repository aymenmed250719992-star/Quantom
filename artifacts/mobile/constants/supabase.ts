import AsyncStorage from "@react-native-async-storage/async-storage";
import { getApiBase } from "./api";

export const SUPABASE_URL_KEY   = "quantom_supabase_url_v1";
export const SUPABASE_ANON_KEY  = "quantom_supabase_anon_v1";

const BAKED_URL  = process.env.EXPO_PUBLIC_SUPABASE_URL  ?? "";
const BAKED_ANON = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY ?? "";

let _url:  string = BAKED_URL;
let _anon: string = BAKED_ANON;

export function getSupabaseUrl():  string { return _url;  }
export function getSupabaseAnon(): string { return _anon; }
export function isSupabaseConfigured(): boolean { return _url.length > 10 && _anon.length > 10; }

export async function loadSupabaseConfig(): Promise<void> {
  try {
    const [u, a] = await Promise.all([
      AsyncStorage.getItem(SUPABASE_URL_KEY),
      AsyncStorage.getItem(SUPABASE_ANON_KEY),
    ]);
    if (u && u.length > 10) _url  = u;
    if (a && a.length > 10) _anon = a;
  } catch {}
}

export async function saveSupabaseConfig(url: string, anon: string): Promise<void> {
  const u = url.trim().replace(/\/$/, "");
  const a = anon.trim();
  _url  = u;
  _anon = a;
  await Promise.all([
    AsyncStorage.setItem(SUPABASE_URL_KEY,  u).catch(() => {}),
    AsyncStorage.setItem(SUPABASE_ANON_KEY, a).catch(() => {}),
  ]);
}

export async function testSupabaseViaBackend(): Promise<{ ok: boolean; connected?: boolean; error?: string }> {
  try {
    const res = await fetch(`${getApiBase()}/supabase/status`, { signal: AbortSignal.timeout(8000) });
    const d   = await res.json();
    return { ok: true, connected: d?.connected };
  } catch (e: any) {
    return { ok: false, error: String(e) };
  }
}

export async function supabaseQuery(
  table: string,
  type: "select" | "insert" | "update" | "delete" | "upsert" = "select",
  opts: { filters?: Record<string,any>; data?: Record<string,any>; limit?: number } = {}
): Promise<{ ok: boolean; data?: any[]; count?: number; error?: string }> {
  try {
    const res = await fetch(`${getApiBase()}/supabase/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ table, type, ...opts }),
      signal: AbortSignal.timeout(10000),
    });
    return await res.json();
  } catch (e: any) {
    return { ok: false, error: String(e) };
  }
}
