import AsyncStorage from "@react-native-async-storage/async-storage";
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";

import { autoDiscoverServer, getApiBase, getWsUrl, loadServerDomain, safeJson } from "@/constants/api";
import { useNotify } from "@/context/NotificationContext";
import type {
  BalanceInfo,
  BotStatus,
  Portfolio,
  Settings,
  Trade,
  WsMessage,
} from "@/types";

const MAX_LOGS = 80;
const STORAGE_KEY = "bot_settings_v2";

export interface AutoExplain {
  id: string;
  text: string;
  provider: string;
  tradeInfo: string;
  isWin: boolean;
}

interface BotContextType {
  status: BotStatus | null;
  balance: BalanceInfo | null;
  trades: Trade[];
  portfolio: Portfolio | null;
  logs: string[];
  settings: Settings;
  isConnected: boolean;
  isStatusLoading: boolean;
  isBalanceLoading: boolean;
  isTradesLoading: boolean;
  isPortfolioLoading: boolean;
  autoExplain: AutoExplain | null;
  clearAutoExplain: () => void;
  startBot: () => Promise<void>;
  stopBot: () => Promise<void>;
  setMode: (mode: "demo" | "live") => Promise<void>;
  refreshStatus: () => Promise<void>;
  refreshBalance: () => Promise<void>;
  refreshTrades: () => Promise<void>;
  refreshPortfolio: () => Promise<void>;
  updateSettings: (s: Partial<Settings>) => Promise<void>;
  clearLogs: () => void;
}

const BotContext = createContext<BotContextType | null>(null);

export function useBotContext() {
  const ctx = useContext(BotContext);
  if (!ctx) throw new Error("useBotContext must be inside BotProvider");
  return ctx;
}

async function apiFetch(path: string, options?: RequestInit) {
  const res = await fetch(`${getApiBase()}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
  const data = await safeJson(res);
  if (data === null) throw new Error(`API ${path} → non-JSON response`);
  return data;
}

export function BotProvider({ children }: { children: React.ReactNode }) {
  const notify = useNotify();
  const [status, setStatus] = useState<BotStatus | null>(null);
  const [balance, setBalance] = useState<BalanceInfo | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [logs, setLogs] = useState<string[]>(["Connecting to autopilot..."]);
  const [settings, setSettings] = useState<Settings>({
    maxRiskPercent: 1.5,
    minConfidenceScore: 70,
    targetWinRate: 65,
  });
  const [isConnected, setIsConnected] = useState(false);
  const [isStatusLoading, setIsStatusLoading] = useState(false);
  const [isBalanceLoading, setIsBalanceLoading] = useState(false);
  const [isTradesLoading, setIsTradesLoading] = useState(false);
  const [autoExplain, setAutoExplain] = useState<AutoExplain | null>(null);
  const [isPortfolioLoading, setIsPortfolioLoading] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptsRef = useRef(0);

  const addLog = useCallback((msg: string) => {
    setLogs((prev) => [msg, ...prev].slice(0, MAX_LOGS));
  }, []);

  const refreshStatus = useCallback(async () => {
    setIsStatusLoading(true);
    try {
      const data = await apiFetch("/status");
      setStatus(data);
      if (data.target_win_rate !== undefined) {
        setSettings((prev) => ({ ...prev, targetWinRate: data.target_win_rate }));
      }
    } catch {
      /* backend not yet reachable */
    } finally {
      setIsStatusLoading(false);
    }
  }, []);

  const refreshBalance = useCallback(async () => {
    setIsBalanceLoading(true);
    try {
      const data = await apiFetch("/balance");
      setBalance(data);
    } catch {
      /* ignore */
    } finally {
      setIsBalanceLoading(false);
    }
  }, []);

  const refreshTrades = useCallback(async () => {
    setIsTradesLoading(true);
    try {
      const data = await apiFetch("/trades");
      setTrades(data.trades ?? []);
    } catch {
      /* ignore */
    } finally {
      setIsTradesLoading(false);
    }
  }, []);

  const refreshPortfolio = useCallback(async () => {
    setIsPortfolioLoading(true);
    try {
      const data = await apiFetch("/portfolio");
      setPortfolio(data);
    } catch {
      /* ignore */
    } finally {
      setIsPortfolioLoading(false);
    }
  }, []);

  // Use a ref so connectWs can call fetchAutoExplain even though it's
  // defined later in the render function (avoids stale-closure issues).
  const fetchAutoExplainRef = useRef<((sym: string, pnl: string, isWin: boolean) => void) | undefined>(undefined);

  const connectWs = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
    }
    const ws = new WebSocket(getWsUrl());
    wsRef.current = ws;

    ws.onopen = () => setIsConnected(true);

    ws.onmessage = (event) => {
      try {
        const msg: WsMessage = JSON.parse(event.data as string);
        if (msg.type === "pong") return;
        if (msg.message) addLog(msg.message);

        // ── In-app Notification Triggers ─────────────────────────
        const m = msg.message ?? "";

        if (msg.type === "trade") {
          refreshTrades();
          refreshStatus();
          refreshPortfolio();

          // Trade closed — TP hit (win)
          if (m.includes("TP ✅")) {
            const sym  = m.match(/\[TP ✅\]\s*(\S+)/)?.[1] ?? "Trade";
            const pnl  = m.match(/PnL:\s*\$([+-]?[\d.]+)/)?.[1] ?? "0";
            notify("win", `✅ ربح — ${sym}`, `PnL: $${pnl}`);
            fetchAutoExplainRef.current?.(sym, pnl, true);

          // Trade closed — SL hit (loss)
          } else if (m.includes("SL 🔴")) {
            const sym  = m.match(/\[SL 🔴\]\s*(\S+)/)?.[1] ?? "Trade";
            const pnl  = m.match(/PnL:\s*\$([+-]?[\d.]+)/)?.[1] ?? "0";
            notify("loss", `🔴 Stop Loss — ${sym}`, `PnL: $${pnl}`);
            fetchAutoExplainRef.current?.(sym, pnl, false);

          // New BUY trade opened
          } else if (m.includes("✅ BUY")) {
            const sym  = m.match(/BUY\s+(\S+)\s+@/)?.[1] ?? "Trade";
            const conf = m.match(/(\d+)%/)?.[1];
            notify("signal", `📊 إشارة شراء — ${sym}`, conf ? `ثقة: ${conf}%` : "صفقة جديدة مفتوحة");
          }

        } else if (msg.type === "adaptive") {
          refreshTrades();
          refreshStatus();
          refreshPortfolio();

        // Agent events: emergency / drawdown / win streak
        } else if (msg.type === "agent") {
          if (m.includes("EMERGENCY HALT")) {
            notify("emergency", "🛑 إيقاف طارئ!", "5 خسائر متتالية — البوت موقف مؤقتاً للمراجعة");
          } else if (m.includes("DRAWDOWN ALERT")) {
            notify("alert", "⚠️ تنبيه انخفاض", "3 خسائر متتالية — تم رفع عتبة الثقة");
          } else if (m.includes("WIN STREAK")) {
            notify("win", "🏆 سلسلة فوز!", "5 صفقات رابحة متتالية — أداء ممتاز");
          }
        }
        // ─────────────────────────────────────────────────────────

      } catch {
        /* ignore */
      }
    };

    ws.onerror = () => setIsConnected(false);

    ws.onclose = () => {
      setIsConnected(false);
      reconnectAttemptsRef.current += 1;
      const attempts = reconnectAttemptsRef.current;

      // Every 4 failures → re-discover the server (handles server restarts)
      if (attempts % 4 === 0) {
        autoDiscoverServer(true).then(() => {
          reconnectTimerRef.current = setTimeout(connectWs, 2000);
        });
      } else {
        // Exponential backoff: 3s, 6s, 10s, then settle at 10s
        const delay = Math.min(3000 * Math.pow(1.5, Math.min(attempts - 1, 3)), 10000);
        reconnectTimerRef.current = setTimeout(connectWs, delay);
      }
    };
  }, [addLog, refreshTrades, refreshStatus, refreshPortfolio]);

  useEffect(() => {
    // Auto-discover server first (handles URL changes after server restart)
    // then load saved settings and connect
    autoDiscoverServer().then(() => {
      loadServerDomain().then(() => {
        AsyncStorage.getItem(STORAGE_KEY).then((raw) => {
          if (raw) {
            try { setSettings(JSON.parse(raw)); } catch { /* ignore */ }
          }
        });
        reconnectAttemptsRef.current = 0;
        refreshStatus();
        refreshBalance();
        refreshTrades();
        refreshPortfolio();
        connectWs();
      });
    });

    const interval = setInterval(() => {
      refreshStatus();
      refreshPortfolio();
    }, 30000);

    return () => {
      clearInterval(interval);
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      wsRef.current?.close();
    };
  }, [connectWs, refreshStatus, refreshBalance, refreshTrades, refreshPortfolio]);

  const startBot = useCallback(async () => {
    await apiFetch("/bot/start", { method: "POST" });
    await refreshStatus();
  }, [refreshStatus]);

  const stopBot = useCallback(async () => {
    await apiFetch("/bot/stop", { method: "POST" });
    await refreshStatus();
  }, [refreshStatus]);

  const setMode = useCallback(
    async (mode: "demo" | "live") => {
      await apiFetch("/mode", { method: "POST", body: JSON.stringify({ mode }) });
      await refreshStatus();
    },
    [refreshStatus]
  );

  const updateSettings = useCallback(async (partial: Partial<Settings>) => {
    setSettings((prev) => {
      const next = { ...prev, ...partial };
      AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      return next;
    });
    try {
      await apiFetch("/settings", {
        method: "POST",
        body: JSON.stringify({
          max_risk_percent: partial.maxRiskPercent,
          min_confidence_score: partial.minConfidenceScore,
          target_win_rate: partial.targetWinRate,
        }),
      });
    } catch {
      /* ignore */
    }
  }, []);

  const clearLogs = useCallback(() => setLogs([]), []);

  const clearAutoExplain = useCallback(() => setAutoExplain(null), []);

  const fetchAutoExplain = useCallback(async (sym: string, pnl: string, isWin: boolean): Promise<void> => {
    try {
      const tradeInfo = `${isWin ? "✅ ربح" : "🔴 خسارة"} — ${sym} | PnL: $${pnl}`;
      const question  = isWin
        ? `لقد أغلقت صفقة ${sym} برصيد +$${pnl}. اشرح لي في جملتين: لماذا نجحت هذه الصفقة وما الدرس المستفاد منها؟`
        : `لقد أغلقت صفقة ${sym} بخسارة $${pnl}. اشرح لي في جملتين: لماذا فشلت وما الدرس المستفاد؟`;
      const res = await fetch(`${getApiBase()}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: question }),
      });
      if (!res.ok) return;
      const data = await safeJson(res);
      if (data?.response) {
        setAutoExplain({
          id: Date.now().toString(),
          text: data.response,
          provider: data.provider ?? "rule-based",
          tradeInfo,
          isWin,
        });
      }
    } catch {
      /* ignore */
    }
  }, []);

  // Keep ref in sync so connectWs (defined earlier) always calls latest version
  fetchAutoExplainRef.current = fetchAutoExplain;

  return (
    <BotContext.Provider
      value={{
        status,
        balance,
        trades,
        portfolio,
        logs,
        settings,
        isConnected,
        isStatusLoading,
        isBalanceLoading,
        isTradesLoading,
        isPortfolioLoading,
        autoExplain,
        clearAutoExplain,
        startBot,
        stopBot,
        setMode,
        refreshStatus,
        refreshBalance,
        refreshTrades,
        refreshPortfolio,
        updateSettings,
        clearLogs,
      }}
    >
      {children}
    </BotContext.Provider>
  );
}
