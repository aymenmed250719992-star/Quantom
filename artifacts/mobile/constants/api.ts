import AsyncStorage from "@react-native-async-storage/async-storage";

export const SERVER_URL_KEY = "quantom_server_domain_v1";
export const AUTO_DISCOVER_KEY = "quantom_auto_discovered_v1";

const BAKED_DOMAIN = (process.env.EXPO_PUBLIC_DOMAIN ?? "")
  .replace(/^https?:\/\//, "")
  .replace(/\/+$/, "");

const CANDIDATE_DOMAINS: string[] = [
  BAKED_DOMAIN,
].filter((d) => d.length > 4);

let _domain: string = CANDIDATE_DOMAINS[0] ?? "";

export function getApiBase(): string {
  const p = _domain.startsWith("localhost") ? "http" : "https";
  return `${p}://${_domain}/trade`;
}

export function getWsUrl(): string {
  const p = _domain.startsWith("localhost") ? "ws" : "wss";
  return `${p}://${_domain}/trade/ws`;
}

export function getServerDomain(): string {
  return _domain;
}

export function setServerDomain(raw: string): void {
  const clean = raw.trim().replace(/^https?:\/\//, "").replace(/\/+$/, "");
  if (clean) _domain = clean;
}

export async function loadServerDomain(): Promise<void> {
  try {
    const saved = await AsyncStorage.getItem(SERVER_URL_KEY);
    if (saved && saved.length > 3) {
      _domain = saved;
    }
  } catch {}
}

export async function saveServerDomain(raw: string): Promise<void> {
  const clean = raw.trim().replace(/^https?:\/\//, "").replace(/\/+$/, "");
  if (!clean) return;
  _domain = clean;
  await AsyncStorage.setItem(SERVER_URL_KEY, clean).catch(() => {});
  await AsyncStorage.setItem(AUTO_DISCOVER_KEY, clean).catch(() => {});
}

export function resetServerDomain(): void {
  _domain = CANDIDATE_DOMAINS[0] ?? "";
  AsyncStorage.removeItem(SERVER_URL_KEY).catch(() => {});
  AsyncStorage.removeItem(AUTO_DISCOVER_KEY).catch(() => {});
}

async function pingDomain(domain: string, timeoutMs = 5000): Promise<boolean> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const protocol = domain.startsWith("localhost") ? "http" : "https";
    const res = await fetch(`${protocol}://${domain}/trade/health`, {
      signal: controller.signal,
      method: "GET",
    });
    clearTimeout(timer);
    return res.ok;
  } catch {
    clearTimeout(timer);
    return false;
  }
}

export async function autoDiscoverServer(force = false): Promise<string | null> {
  if (!force) {
    try {
      const cached = await AsyncStorage.getItem(AUTO_DISCOVER_KEY);
      if (cached && cached.length > 3) {
        const ok = await pingDomain(cached, 5000);
        if (ok) {
          _domain = cached;
          await AsyncStorage.setItem(SERVER_URL_KEY, cached).catch(() => {});
          return cached;
        }
      }
    } catch {}
  }

  const candidates = [...new Set(CANDIDATE_DOMAINS)].filter(Boolean);

  const results = await Promise.allSettled(
    candidates.map(async (domain) => {
      const ok = await pingDomain(domain, 5000);
      if (!ok) throw new Error("unreachable");
      return domain;
    })
  );

  for (const r of results) {
    if (r.status === "fulfilled") {
      const found = r.value;
      _domain = found;
      await AsyncStorage.setItem(SERVER_URL_KEY, found).catch(() => {});
      await AsyncStorage.setItem(AUTO_DISCOVER_KEY, found).catch(() => {});
      return found;
    }
  }

  return null;
}

export const DEFAULT_SERVER_DOMAIN = CANDIDATE_DOMAINS[0] ?? "";

/** Safe JSON parser — returns null if response is HTML/empty instead of throwing */
export async function safeJson<T = any>(res: Response): Promise<T | null> {
  try {
    const ct = res.headers.get("content-type") ?? "";
    if (!ct.includes("application/json")) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}
