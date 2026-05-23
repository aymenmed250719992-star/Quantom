import { Feather } from "@expo/vector-icons";
import AsyncStorage from "@react-native-async-storage/async-storage";
import * as Haptics from "expo-haptics";
import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Animated,
  Platform,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { LogFeed } from "@/components/LogFeed";
import { TradeCard } from "@/components/TradeCard";
import { getApiBase, safeJson } from "@/constants/api";
import { useBotContext } from "@/context/BotContext";
import { useColors } from "@/hooks/useColors";
import type { GeminiPoolStatus } from "@/types";

const DEMO_START_KEY = "demo_start_ts_v1";
const TARGET_TRADES = 30;
const TARGET_WIN_DAYS = 14;

// ── Helpers ──────────────────────────────────────────────────────────────────

function clamp(v: number, min = 0, max = 1) {
  return Math.min(max, Math.max(min, v));
}

function daysSince(ts: number) {
  return (Date.now() - ts) / 86_400_000;
}

// ── Sub-components ───────────────────────────────────────────────────────────

function PulsingDot({ active, color }: { active: boolean; color: string }) {
  const scale = useRef(new Animated.Value(1)).current;
  const opacity = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    if (!active) return;
    const pulse = Animated.loop(
      Animated.sequence([
        Animated.parallel([
          Animated.timing(scale, { toValue: 1.8, duration: 900, useNativeDriver: true }),
          Animated.timing(opacity, { toValue: 0, duration: 900, useNativeDriver: true }),
        ]),
        Animated.parallel([
          Animated.timing(scale, { toValue: 1, duration: 0, useNativeDriver: true }),
          Animated.timing(opacity, { toValue: 1, duration: 0, useNativeDriver: true }),
        ]),
      ])
    );
    pulse.start();
    return () => pulse.stop();
  }, [active, scale, opacity]);

  return (
    <View style={{ width: 10, height: 10, alignItems: "center", justifyContent: "center" }}>
      {active && (
        <Animated.View
          style={{
            position: "absolute",
            width: 10,
            height: 10,
            borderRadius: 5,
            backgroundColor: color,
            transform: [{ scale }],
            opacity,
          }}
        />
      )}
      <View style={{ width: 7, height: 7, borderRadius: 3.5, backgroundColor: color }} />
    </View>
  );
}

function WinRateBar({
  actual, target, primaryColor, warningColor, bgColor,
}: {
  actual: number; target: number; primaryColor: string; warningColor: string; bgColor: string;
}) {
  const barColor = actual >= target ? primaryColor : warningColor;
  const pct = clamp(actual, 0, 100);
  const targetPct = clamp(target, 0, 100);
  return (
    <View style={bar.wrap}>
      <View style={[bar.track, { backgroundColor: bgColor }]}>
        <View style={[bar.fill, { width: `${pct}%` as any, backgroundColor: barColor }]} />
        <View style={[bar.marker, { left: `${targetPct}%` as any, backgroundColor: warningColor }]} />
      </View>
      <View style={bar.labels}>
        <Text style={[bar.label, { color: barColor }]}>{actual.toFixed(1)}%</Text>
        <Text style={[bar.labelRight, { color: warningColor }]}>target {target.toFixed(0)}%</Text>
      </View>
    </View>
  );
}

const bar = StyleSheet.create({
  wrap: { marginTop: 14 },
  track: { height: 5, borderRadius: 3, position: "relative", overflow: "visible" },
  fill: { height: 5, borderRadius: 3, position: "absolute", left: 0, top: 0 },
  marker: { position: "absolute", width: 2, height: 12, borderRadius: 1, top: -3.5, marginLeft: -1 },
  labels: { flexDirection: "row", justifyContent: "space-between", marginTop: 6 },
  label: { fontSize: 11, fontFamily: "monospace", fontWeight: "700" as const },
  labelRight: { fontSize: 10, fontFamily: "monospace" },
});

const PROVIDER_COLORS: Record<string, string> = {
  gemini: "#4285F4",
  openai: "#10A37F",
  claude: "#D97706",
};
const PROVIDER_ICONS: Record<string, string> = {
  gemini: "zap",
  openai: "message-circle",
  claude: "feather",
};

// ── AI Keys strip ─────────────────────────────────────────────────────────────

function GeminiKeysStrip() {
  const colors = useColors();
  const [pool, setPool] = useState<GeminiPoolStatus | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch(`${getApiBase()}/ai/providers`);
      if (res.ok) setPool(await safeJson(res));
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 60_000);
    return () => clearInterval(t);
  }, [refresh]);

  if (!pool || pool.total_keys === 0) return null;

  const accentAll = pool.all_exhausted
    ? colors.destructive
    : pool.available_keys < pool.total_keys
    ? (colors.warning ?? "#FF9F43")
    : colors.primary;

  const activeProviderColor = pool.active_provider
    ? PROVIDER_COLORS[pool.active_provider] ?? colors.primary
    : colors.mutedForeground;

  return (
    <View style={[gk.wrap, { backgroundColor: colors.card, borderColor: `${accentAll}33` }]}>
      <View style={gk.header}>
        <View style={gk.headerLeft}>
          <View style={[gk.dot, { backgroundColor: accentAll }]} />
          <Text style={[gk.title, { color: colors.mutedForeground }]}>AI KEYS</Text>
        </View>
        <View style={gk.headerRight}>
          {pool.active_provider && (
            <View style={[gk.activeBadge, { backgroundColor: `${activeProviderColor}18`, borderColor: `${activeProviderColor}44` }]}>
              <Text style={[gk.activeBadgeTxt, { color: activeProviderColor }]}>
                {pool.active_provider.toUpperCase()}
              </Text>
            </View>
          )}
          <Text style={[gk.summary, {
            color: pool.all_exhausted ? colors.destructive : pool.available_keys < pool.total_keys ? (colors.warning ?? "#FF9F43") : colors.primary,
          }]}>
            {pool.available_keys}/{pool.total_keys} active
          </Text>
        </View>
      </View>

      <View style={gk.keysRow}>
        {pool.keys.map((k, i) => {
          const providerColor = PROVIDER_COLORS[k.provider] ?? colors.primary;
          const keyColor = k.available ? providerColor : k.exhausted ? (colors.warning ?? "#FF9F43") : colors.mutedForeground;
          const isActive = k.label === pool.active_key && k.available;

          return (
            <View
              key={i}
              style={[gk.keyChip, { backgroundColor: `${keyColor}14`, borderColor: isActive ? `${keyColor}66` : `${keyColor}28` }]}
            >
              <Feather name={(PROVIDER_ICONS[k.provider] ?? "key") as any} size={8} color={keyColor} />
              <Text style={[gk.keyLabel, { color: keyColor }]}>
                {k.provider === "gemini" ? "G" : k.provider === "openai" ? "O" : "C"}{i + 1}
              </Text>
              {k.exhausted && k.hours_remaining > 0 ? (
                <Text style={[gk.keyHrs, { color: colors.mutedForeground }]}>{k.hours_remaining.toFixed(0)}h</Text>
              ) : isActive ? (
                <Text style={[gk.keyActive, { color: keyColor }]}>●</Text>
              ) : null}
            </View>
          );
        })}

        {pool.total_keys < 5 && (
          <View style={[gk.keyChip, { backgroundColor: `${colors.mutedForeground}08`, borderColor: colors.border }]}>
            <Feather name="plus" size={8} color={colors.mutedForeground} />
            <Text style={[gk.keyLabel, { color: colors.mutedForeground }]}>Add</Text>
          </View>
        )}
      </View>

      {pool.all_exhausted && (
        <Text style={[gk.exhaustedNote, { color: colors.warning ?? "#FF9F43" }]}>
          ⚠ جميع المفاتيح في فترة راحة — البوت يعمل بالقواعد الآلية
        </Text>
      )}
    </View>
  );
}

const gk = StyleSheet.create({
  wrap: { marginHorizontal: 16, marginTop: 10, borderRadius: 12, borderWidth: 1, padding: 12 },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 10 },
  headerLeft: { flexDirection: "row", alignItems: "center", gap: 6 },
  dot: { width: 6, height: 6, borderRadius: 3 },
  title: { fontSize: 8, fontWeight: "700" as const, letterSpacing: 2 },
  summary: { fontSize: 9, fontFamily: "monospace", fontWeight: "700" as const },
  keysRow: { flexDirection: "row", gap: 8, flexWrap: "wrap" },
  keyChip: {
    flexDirection: "row", alignItems: "center", gap: 5,
    paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, borderWidth: 1,
  },
  keyDot: { width: 5, height: 5, borderRadius: 2.5 },
  keyLabel: { fontSize: 10, fontWeight: "700" as const, fontFamily: "monospace" },
  keyHrs: { fontSize: 8, fontFamily: "monospace" },
  keyActive: { fontSize: 7 },
  exhaustedNote: { fontSize: 9, marginTop: 8, textAlign: "center" as const },
  headerRight: { flexDirection: "row" as const, alignItems: "center" as const, gap: 8 },
  activeBadge: { paddingHorizontal: 7, paddingVertical: 2, borderRadius: 6, borderWidth: 1 },
  activeBadgeTxt: { fontSize: 8, fontWeight: "800" as const, letterSpacing: 0.5 },
});

// ── Live-Readiness card ───────────────────────────────────────────────────────

interface ReadinessCriterion {
  label: string;
  icon: string;
  current: string;
  target: string;
  pct: number; // 0-1
  done: boolean;
}

function ReadinessCard({
  criteria,
  score,
  ready,
}: {
  criteria: ReadinessCriterion[];
  score: number; // 0-100
  ready: boolean;
}) {
  const colors = useColors();
  const accent = ready ? colors.primary : (colors.warning ?? "#FF9F43");

  return (
    <View style={[rc.card, { backgroundColor: colors.card, borderColor: `${accent}44` }]}>
      {/* Header */}
      <View style={rc.header}>
        <View style={rc.headerLeft}>
          <View style={[rc.dot, { backgroundColor: accent }]} />
          <Text style={[rc.title, { color: colors.mutedForeground }]}>LIVE READINESS</Text>
        </View>
        <View style={[rc.scoreBadge, { backgroundColor: `${accent}18`, borderColor: `${accent}44` }]}>
          <Text style={[rc.scoreNum, { color: accent }]}>{score.toFixed(0)}%</Text>
        </View>
      </View>

      {/* Master progress bar */}
      <View style={[rc.masterTrack, { backgroundColor: colors.muted }]}>
        <View style={[rc.masterFill, { width: `${score}%` as any, backgroundColor: accent }]} />
      </View>

      {ready ? (
        <View style={[rc.readyBanner, { backgroundColor: `${colors.primary}15`, borderColor: `${colors.primary}33` }]}>
          <Feather name="check-circle" size={13} color={colors.primary} />
          <Text style={[rc.readyText, { color: colors.primary }]}>
            جاهز للتداول الحقيقي — يمكنك التحويل الآن
          </Text>
        </View>
      ) : null}

      {/* Criteria grid */}
      <View style={rc.grid}>
        {criteria.map((c) => (
          <View key={c.label} style={[rc.criterion, { borderColor: colors.border }]}>
            <View style={rc.criTop}>
              <Feather
                name={c.done ? "check-circle" : (c.icon as any)}
                size={12}
                color={c.done ? colors.primary : colors.mutedForeground}
              />
              <Text style={[rc.criLabel, { color: colors.mutedForeground }]}>{c.label}</Text>
            </View>
            <View style={[rc.criBar, { backgroundColor: colors.muted }]}>
              <View
                style={[
                  rc.criBarFill,
                  {
                    width: `${clamp(c.pct) * 100}%` as any,
                    backgroundColor: c.done ? colors.primary : accent,
                  },
                ]}
              />
            </View>
            <View style={rc.criBottom}>
              <Text style={[rc.criCurrent, { color: c.done ? colors.primary : colors.foreground }]}>
                {c.current}
              </Text>
              <Text style={[rc.criTarget, { color: colors.mutedForeground }]}>/ {c.target}</Text>
            </View>
          </View>
        ))}
      </View>
    </View>
  );
}

const rc = StyleSheet.create({
  card: {
    marginHorizontal: 16,
    marginTop: 10,
    borderRadius: 14,
    borderWidth: 1.5,
    padding: 16,
    gap: 12,
  },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  headerLeft: { flexDirection: "row", alignItems: "center", gap: 8 },
  dot: { width: 3, height: 14, borderRadius: 2 },
  title: { fontSize: 9, fontWeight: "700" as const, letterSpacing: 2 },
  scoreBadge: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 8,
    borderWidth: 1,
  },
  scoreNum: { fontSize: 14, fontWeight: "800" as const, fontFamily: "monospace" },
  masterTrack: { height: 4, borderRadius: 2, overflow: "hidden" },
  masterFill: { height: 4, borderRadius: 2 },
  readyBanner: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    padding: 10,
    borderRadius: 8,
    borderWidth: 1,
  },
  readyText: { fontSize: 12, fontWeight: "600" as const, flex: 1 },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  criterion: {
    flex: 1,
    minWidth: "44%",
    borderWidth: 1,
    borderRadius: 10,
    padding: 10,
    gap: 6,
  },
  criTop: { flexDirection: "row", alignItems: "center", gap: 5 },
  criLabel: { fontSize: 8, fontWeight: "700" as const, letterSpacing: 1 },
  criBar: { height: 3, borderRadius: 2, overflow: "hidden" },
  criBarFill: { height: 3, borderRadius: 2 },
  criBottom: { flexDirection: "row", alignItems: "baseline", gap: 3 },
  criCurrent: { fontSize: 16, fontWeight: "700" as const, fontFamily: "monospace" },
  criTarget: { fontSize: 10, fontFamily: "monospace" },
});

// ── Sentiment Card ────────────────────────────────────────────────────────────

interface SentimentData {
  summary: {
    fng_value: number;
    fng_label: string;
    fng_emoji: string;
    fng_advice_ar: string;
    overall_sentiment: string;
    whale_count: number;
    high_severity_whales: number;
  };
  fear_greed: { color: string; history: { value: number; label: string }[] };
  whale_signals: { symbol: string; message: string; severity: string; direction: string }[];
}

function SentimentCard({ colors }: { colors: any }) {
  const [data, setData] = useState<SentimentData | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${getApiBase()}/sentiment`);
      if (res.ok) setData(await safeJson(res));
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); const t = setInterval(load, 300_000); return () => clearInterval(t); }, [load]);

  if (loading) return null;
  if (!data) return null;

  const s = data.summary;
  const fngColor = data.fear_greed?.color ?? colors.primary;
  const history  = data.fear_greed?.history ?? [];
  const maxH = Math.max(...history.map(h => h.value), 1);

  return (
    <View style={[sc.card, { backgroundColor: colors.card, borderColor: `${fngColor}33` }]}>
      <View style={sc.row}>
        <View style={[sc.iconBox, { backgroundColor: `${fngColor}15` }]}>
          <Text style={sc.emoji}>{s.fng_emoji}</Text>
        </View>
        <View style={{ flex: 1, gap: 2 }}>
          <View style={sc.topRow}>
            <Text style={[sc.label, { color: colors.mutedForeground }]}>MARKET SENTIMENT</Text>
            <View style={[sc.pill, { backgroundColor: `${fngColor}22`, borderColor: `${fngColor}44` }]}>
              <Text style={[sc.pillTxt, { color: fngColor }]}>{s.fng_label}</Text>
            </View>
          </View>
          <Text style={[sc.value, { color: fngColor }]}>{s.fng_value}<Text style={[sc.valueSub, { color: colors.mutedForeground }]}>/100</Text></Text>
          <Text style={[sc.advice, { color: colors.mutedForeground }]} numberOfLines={1}>{s.fng_advice_ar}</Text>
        </View>
      </View>

      {/* 7-day mini bar chart */}
      {history.length > 1 && (
        <View style={sc.bars}>
          {[...history].reverse().map((h, i) => {
            const pct = h.value / maxH;
            const c = h.value <= 30 ? "#ef4444" : h.value <= 50 ? "#f97316" : h.value <= 70 ? "#eab308" : "#22c55e";
            return (
              <View key={i} style={sc.barCol}>
                <View style={[sc.barFill, { height: Math.max(3, pct * 28), backgroundColor: c }]} />
              </View>
            );
          })}
        </View>
      )}

      {/* Whale alerts */}
      {s.whale_count > 0 && (
        <View style={[sc.whaleRow, { borderTopColor: colors.border }]}>
          <Feather name="activity" size={10} color={s.high_severity_whales > 0 ? "#ef4444" : "#f97316"} />
          <Text style={[sc.whaleTxt, { color: colors.mutedForeground }]}>
            {s.whale_count} نشاط غير عادي{s.high_severity_whales > 0 ? ` — ${s.high_severity_whales} عالي الخطورة` : ""}
          </Text>
        </View>
      )}
    </View>
  );
}

const sc = StyleSheet.create({
  card:     { marginHorizontal: 16, marginTop: 10, borderRadius: 14, borderWidth: 1.5, padding: 14, gap: 10 },
  row:      { flexDirection: "row" as const, gap: 12, alignItems: "center" as const },
  iconBox:  { width: 44, height: 44, borderRadius: 12, alignItems: "center" as const, justifyContent: "center" as const },
  emoji:    { fontSize: 22 },
  topRow:   { flexDirection: "row" as const, alignItems: "center" as const, justifyContent: "space-between" as const },
  label:    { fontSize: 8, fontWeight: "700" as const, letterSpacing: 1.5 },
  pill:     { paddingHorizontal: 7, paddingVertical: 2, borderRadius: 6, borderWidth: 1 },
  pillTxt:  { fontSize: 9, fontWeight: "700" as const },
  value:    { fontSize: 28, fontWeight: "800" as const, fontFamily: "monospace", letterSpacing: -1 },
  valueSub: { fontSize: 14, fontWeight: "400" as const },
  advice:   { fontSize: 10, lineHeight: 14 },
  bars:     { flexDirection: "row" as const, gap: 3, alignItems: "flex-end" as const, height: 32 },
  barCol:   { flex: 1, alignItems: "center" as const, justifyContent: "flex-end" as const },
  barFill:  { width: "100%", borderRadius: 2 },
  whaleRow: { flexDirection: "row" as const, gap: 6, alignItems: "center" as const, paddingTop: 8, borderTopWidth: 1 },
  whaleTxt: { fontSize: 10 },
});

// ── Main screen ───────────────────────────────────────────────────────────────

export default function DashboardScreen() {
  const colors = useColors();
  const insets = useSafeAreaInsets();
  const {
    status, balance, trades, portfolio, logs,
    isConnected, isStatusLoading, isBalanceLoading,
    startBot, stopBot, refreshStatus, refreshBalance,
    refreshTrades, refreshPortfolio, clearLogs,
  } = useBotContext();

  const [isToggling, setIsToggling] = useState(false);
  const [demoStartTs, setDemoStartTs] = useState<number | null>(null);

  const topPad    = Platform.OS === "web" ? 67 : insets.top;
  const bottomPad = Platform.OS === "web" ? 34 : insets.bottom;

  const isRunning      = status?.is_running ?? false;
  const isLive         = status?.mode === "live";
  const totalPnl       = portfolio?.total_pnl ?? 0;
  const roiPercent     = portfolio?.roi_percent ?? 0;
  const winRate        = portfolio?.win_rate ?? status?.win_rate ?? 0;
  const targetWinRate  = portfolio?.target_win_rate ?? status?.target_win_rate ?? 65;
  const onTarget       = winRate >= targetWinRate;
  const totalBalance   = balance?.total ?? 0;
  const recentTrades   = trades.slice(0, 4);

  // ── Demo start timestamp tracking ──────────────────────────────────────────
  useEffect(() => {
    AsyncStorage.getItem(DEMO_START_KEY).then((v) => {
      if (v) {
        setDemoStartTs(parseInt(v, 10));
      } else if (isRunning && !isLive) {
        const now = Date.now();
        AsyncStorage.setItem(DEMO_START_KEY, String(now));
        setDemoStartTs(now);
      }
    });
  }, [isRunning, isLive]);

  // Record start the moment autopilot is turned on in demo mode
  useEffect(() => {
    if (isRunning && !isLive && demoStartTs === null) {
      AsyncStorage.getItem(DEMO_START_KEY).then((v) => {
        if (!v) {
          const now = Date.now();
          AsyncStorage.setItem(DEMO_START_KEY, String(now));
          setDemoStartTs(now);
        }
      });
    }
  }, [isRunning, isLive, demoStartTs]);

  // ── Readiness score ────────────────────────────────────────────────────────
  const totalClosed  = portfolio?.total_closed ?? 0;
  const profitFactor = portfolio?.profit_factor ?? 0;
  const daysRunning  = demoStartTs ? daysSince(demoStartTs) : 0;

  const tradesPct  = clamp(totalClosed / TARGET_TRADES);
  const winPct     = clamp(winRate / 65);
  const pfPct      = clamp(profitFactor / 1.3);
  const daysPct    = clamp(daysRunning / TARGET_WIN_DAYS);

  const readinessScore = ((tradesPct + winPct + pfPct + daysPct) / 4) * 100;
  const isReady        = tradesPct >= 1 && winPct >= 1 && pfPct >= 1 && daysPct >= 1;

  const criteria: ReadinessCriterion[] = [
    {
      label: "CLOSED TRADES",
      icon: "bar-chart-2",
      current: String(totalClosed),
      target: `${TARGET_TRADES}`,
      pct: tradesPct,
      done: tradesPct >= 1,
    },
    {
      label: "WIN RATE",
      icon: "trending-up",
      current: `${winRate.toFixed(1)}%`,
      target: "65%",
      pct: winPct,
      done: winPct >= 1,
    },
    {
      label: "PROFIT FACTOR",
      icon: "activity",
      current: profitFactor > 0 ? `${profitFactor.toFixed(2)}x` : "—",
      target: "1.3x",
      pct: pfPct,
      done: pfPct >= 1,
    },
    {
      label: "DAYS RUNNING",
      icon: "clock",
      current: daysRunning >= 1 ? `${Math.floor(daysRunning)}d` : `${Math.round(daysRunning * 24)}h`,
      target: `${TARGET_WIN_DAYS}d`,
      pct: daysPct,
      done: daysPct >= 1,
    },
  ];

  // ── Handlers ───────────────────────────────────────────────────────────────

  const handleBotToggle = async () => {
    if (isToggling) return;
    setIsToggling(true);
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy);
    try {
      if (isRunning) await stopBot();
      else await startBot();
    } finally {
      setIsToggling(false);
    }
  };

  const handleRefresh = async () => {
    await Promise.all([refreshStatus(), refreshBalance(), refreshTrades(), refreshPortfolio()]);
  };

  const roiColor = roiPercent > 0 ? colors.primary : roiPercent < 0 ? colors.destructive : colors.mutedForeground;
  const pnlColor = totalPnl > 0 ? colors.primary : totalPnl < 0 ? colors.destructive : colors.mutedForeground;

  return (
    <ScrollView
      style={[styles.root, { backgroundColor: colors.background }]}
      contentContainerStyle={{ paddingBottom: bottomPad + 90 }}
      showsVerticalScrollIndicator={false}
      refreshControl={
        <RefreshControl
          refreshing={isStatusLoading || isBalanceLoading}
          onRefresh={handleRefresh}
          tintColor={colors.primary}
        />
      }
    >
      {/* ══════════════ HEADER ══════════════ */}
      <View style={[styles.header, { paddingTop: topPad + 12, borderBottomColor: colors.border }]}>
        <View style={styles.headerLeft}>
          <Text style={[styles.brandLabel, { color: colors.mutedForeground }]}>
            ISLAMIC TRADING TERMINAL
          </Text>
          <View style={styles.connRow}>
            <PulsingDot active={isConnected} color={isConnected ? colors.primary : colors.destructive} />
            <Text style={[styles.connLabel, { color: isConnected ? colors.primary : colors.destructive }]}>
              {isConnected ? "CONNECTED" : "OFFLINE"}
            </Text>
            {isLive && (
              <>
                <Text style={[styles.connSep, { color: colors.border }]}>|</Text>
                <View style={[styles.livePill, { backgroundColor: `${colors.destructive}22`, borderColor: `${colors.destructive}55` }]}>
                  <Text style={[styles.liveText, { color: colors.destructive }]}>⬤ LIVE FUNDS</Text>
                </View>
              </>
            )}
          </View>
        </View>
        <View style={styles.headerRight}>
          <Text style={[styles.modeLabel, { color: isLive ? colors.destructive : (colors.cyan ?? "#00D4FF") }]}>
            {isLive ? "LIVE" : "TESTNET"}
          </Text>
          <Text style={[styles.versionLabel, { color: colors.mutedForeground }]}>v2.0</Text>
        </View>
      </View>

      {/* ══════════════ PORTFOLIO ROI HERO ══════════════ */}
      <View style={[styles.heroCard, { backgroundColor: colors.card, borderColor: onTarget ? `${colors.primary}44` : `${colors.warning}33` }]}>
        <View style={styles.heroTop}>
          <View>
            <Text style={[styles.heroLabel, { color: colors.mutedForeground }]}>PORTFOLIO ROI</Text>
            <Text style={[styles.heroROI, { color: roiColor }]}>
              {roiPercent >= 0 ? "+" : ""}{roiPercent.toFixed(2)}
              <Text style={[styles.heroROIPct, { color: roiColor }]}>%</Text>
            </Text>
            <Text style={[styles.heroPnl, { color: pnlColor }]}>
              {totalPnl >= 0 ? "+" : ""}{totalPnl.toFixed(4)} USDT
            </Text>
          </View>
          <View style={styles.heroRight}>
            <View style={[styles.targetBadge, {
              backgroundColor: onTarget ? `${colors.primary}15` : `${colors.warning}15`,
              borderColor: onTarget ? `${colors.primary}44` : `${colors.warning}44`,
            }]}>
              <Feather name={onTarget ? "check-circle" : "alert-circle"} size={11} color={onTarget ? colors.primary : colors.warning} />
              <Text style={[styles.targetBadgeText, { color: onTarget ? colors.primary : colors.warning }]}>
                {onTarget ? "ON TARGET" : "BELOW TARGET"}
              </Text>
            </View>
            <View style={styles.pfBlock}>
              <Text style={[styles.pfLabel, { color: colors.mutedForeground }]}>PROFIT FACTOR</Text>
              <Text style={[styles.pfValue, {
                color: (portfolio?.profit_factor ?? 0) >= 1.5 ? colors.primary
                  : (portfolio?.profit_factor ?? 0) >= 1 ? colors.warning
                  : colors.destructive,
              }]}>
                {portfolio ? portfolio.profit_factor.toFixed(2) : "—"}x
              </Text>
            </View>
          </View>
        </View>
        <WinRateBar
          actual={winRate}
          target={targetWinRate}
          primaryColor={colors.primary}
          warningColor={colors.warning}
          bgColor={colors.muted}
        />
      </View>

      {/* ══════════════ AUTOPILOT CONTROL ══════════════ */}
      <View style={[styles.autopilotCard, {
        backgroundColor: colors.card,
        borderColor: isRunning ? `${colors.primary}55` : colors.border,
      }]}>
        <View style={styles.autopilotLeft}>
          <PulsingDot active={isRunning} color={isRunning ? colors.primary : colors.mutedForeground} />
          <View style={{ flex: 1 }}>
            <Text style={[styles.autopilotLabel, { color: isRunning ? colors.primary : colors.foreground }]}>
              {isRunning ? "AUTOPILOT RUNNING" : "AUTOPILOT OFFLINE"}
            </Text>
            <Text style={[styles.autopilotSub, { color: colors.mutedForeground }]}>
              {isRunning
                ? `target ${targetWinRate.toFixed(0)}% win · threshold ${status?.current_threshold ?? 70}%`
                : "start to begin autonomous trading"}
            </Text>
          </View>
        </View>
        {isToggling ? (
          <ActivityIndicator color={colors.primary} size="small" />
        ) : (
          <Switch
            value={isRunning}
            onValueChange={handleBotToggle}
            trackColor={{ false: colors.muted, true: `${colors.primary}66` }}
            thumbColor={isRunning ? colors.primary : "#2A4060"}
            ios_backgroundColor={colors.muted}
          />
        )}
      </View>

      {/* ══════════════ MARKET SENTIMENT ══════════════ */}
      <SentimentCard colors={colors} />

      {/* ══════════════ GEMINI AI KEYS STATUS ══════════════ */}
      <GeminiKeysStrip />

      {/* ══════════════ LIVE READINESS (demo mode only) ══════════════ */}
      {!isLive && (
        <ReadinessCard
          criteria={criteria}
          score={readinessScore}
          ready={isReady}
        />
      )}

      {/* ══════════════ METRICS ROW ══════════════ */}
      <View style={styles.metricsRow}>
        <View style={[styles.metricCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
          <Text style={[styles.metricLabel, { color: colors.mutedForeground }]}>BALANCE</Text>
          {isBalanceLoading && !balance ? (
            <ActivityIndicator color={colors.primary} size="small" style={{ marginTop: 6 }} />
          ) : (
            <>
              <Text style={[styles.metricValue, { color: colors.foreground }]}>
                ${totalBalance < 10000 ? totalBalance.toFixed(2) : (totalBalance / 1000).toFixed(1) + "K"}
              </Text>
              <Text style={[styles.metricSub, { color: colors.mutedForeground }]}>USDT</Text>
            </>
          )}
        </View>

        <View style={[styles.metricCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
          <Text style={[styles.metricLabel, { color: colors.mutedForeground }]}>TRADES</Text>
          <Text style={[styles.metricValue, { color: colors.foreground }]}>
            {portfolio?.total_closed ?? status?.total_trades ?? 0}
          </Text>
          <Text style={[styles.metricSub, { color: colors.cyan ?? "#00D4FF" }]}>
            {portfolio?.total_open ?? 0} open
          </Text>
        </View>

        <View style={[styles.metricCard, {
          backgroundColor: colors.card,
          borderColor: onTarget ? `${colors.primary}44` : colors.border,
        }]}>
          <Text style={[styles.metricLabel, { color: colors.mutedForeground }]}>WIN RATE</Text>
          <Text style={[styles.metricValue, { color: onTarget ? colors.primary : colors.warning }]}>
            {winRate.toFixed(1)}%
          </Text>
          <Text style={[styles.metricSub, { color: colors.mutedForeground }]}>/ {targetWinRate.toFixed(0)}% tgt</Text>
        </View>

        <View style={[styles.metricCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
          <Text style={[styles.metricLabel, { color: colors.mutedForeground }]}>THRESH</Text>
          <Text style={[styles.metricValue, { color: colors.cyan ?? "#00D4FF" }]}>
            {status?.current_threshold ?? 70}%
          </Text>
          <Text style={[styles.metricSub, { color: colors.mutedForeground }]}>AI conf.</Text>
        </View>
      </View>

      {/* ══════════════ SCANNER LOG ══════════════ */}
      <View style={styles.section}>
        <View style={styles.sectionHead}>
          <View style={styles.sectionHeadLeft}>
            <View style={[styles.sectionAccent, { backgroundColor: colors.cyan ?? "#00D4FF" }]} />
            <Text style={[styles.sectionTitle, { color: colors.mutedForeground }]}>LIVE SCANNER</Text>
          </View>
          <Pressable onPress={clearLogs}>
            <Text style={[styles.sectionAction, { color: colors.mutedForeground }]}>CLEAR</Text>
          </Pressable>
        </View>
        <LogFeed logs={logs} maxHeight={200} />
      </View>

      {/* ══════════════ RECENT TRADES ══════════════ */}
      <View style={styles.section}>
        <View style={styles.sectionHead}>
          <View style={styles.sectionHeadLeft}>
            <View style={[styles.sectionAccent, { backgroundColor: colors.primary }]} />
            <Text style={[styles.sectionTitle, { color: colors.mutedForeground }]}>RECENT POSITIONS</Text>
          </View>
          {portfolio && (
            <Text style={[styles.sectionAction, { color: colors.mutedForeground }]}>
              {portfolio.wins}W / {portfolio.losses}L
            </Text>
          )}
        </View>

        {recentTrades.length > 0 ? (
          recentTrades.map((trade) => <TradeCard key={trade.id} trade={trade} compact />)
        ) : (
          <View style={[styles.emptyCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
            <Text style={[styles.emptyLine1, { color: "#1E3A5A" }]}>{">"} awaiting first signal...</Text>
            <Text style={[styles.emptyLine2, { color: colors.mutedForeground }]}>
              Start the autopilot to begin scanning
            </Text>
          </View>
        )}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  header: {
    flexDirection: "row", alignItems: "flex-end", justifyContent: "space-between",
    paddingHorizontal: 18, paddingBottom: 14, borderBottomWidth: 1,
  },
  headerLeft: { gap: 6 },
  brandLabel: { fontSize: 9, fontWeight: "700" as const, letterSpacing: 2.5, fontFamily: "monospace" },
  connRow: { flexDirection: "row", alignItems: "center", gap: 7 },
  connLabel: { fontSize: 9, fontWeight: "700" as const, letterSpacing: 1.5, fontFamily: "monospace" },
  connSep: { fontSize: 10 },
  livePill: { paddingHorizontal: 7, paddingVertical: 2, borderRadius: 4, borderWidth: 1 },
  liveText: { fontSize: 8, fontWeight: "700" as const, letterSpacing: 1 },
  headerRight: { alignItems: "flex-end", gap: 2 },
  modeLabel: { fontSize: 11, fontWeight: "700" as const, letterSpacing: 1.5 },
  versionLabel: { fontSize: 9, fontFamily: "monospace" },

  heroCard: { marginHorizontal: 16, marginTop: 16, borderRadius: 14, borderWidth: 1.5, padding: 20 },
  heroTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" },
  heroLabel: { fontSize: 9, letterSpacing: 2, fontWeight: "700" as const, marginBottom: 6 },
  heroROI: { fontSize: 52, fontWeight: "800" as const, fontFamily: "monospace", lineHeight: 56, letterSpacing: -2 },
  heroROIPct: { fontSize: 28, fontWeight: "700" as const },
  heroPnl: { fontSize: 13, fontFamily: "monospace", marginTop: 4, fontWeight: "600" as const },
  heroRight: { alignItems: "flex-end", gap: 12 },
  targetBadge: {
    flexDirection: "row", alignItems: "center", gap: 5,
    paddingHorizontal: 9, paddingVertical: 5, borderRadius: 7, borderWidth: 1,
  },
  targetBadgeText: { fontSize: 9, fontWeight: "700" as const, letterSpacing: 0.8 },
  pfBlock: { alignItems: "flex-end" },
  pfLabel: { fontSize: 8, letterSpacing: 1, fontWeight: "600" as const },
  pfValue: { fontSize: 22, fontWeight: "700" as const, fontFamily: "monospace" },

  autopilotCard: {
    flexDirection: "row", alignItems: "center", gap: 12,
    marginHorizontal: 16, marginTop: 10, borderRadius: 12, borderWidth: 1.5, padding: 16,
  },
  autopilotLeft: { flex: 1, flexDirection: "row", alignItems: "center", gap: 12 },
  autopilotLabel: { fontSize: 12, fontWeight: "700" as const, letterSpacing: 0.5 },
  autopilotSub: { fontSize: 10, marginTop: 2, fontFamily: "monospace" },

  metricsRow: { flexDirection: "row", gap: 8, marginHorizontal: 16, marginTop: 10 },
  metricCard: { flex: 1, borderRadius: 10, borderWidth: 1, padding: 12 },
  metricLabel: { fontSize: 7, letterSpacing: 1.2, fontWeight: "700" as const, marginBottom: 6 },
  metricValue: { fontSize: 16, fontWeight: "700" as const, fontFamily: "monospace", letterSpacing: -0.5 },
  metricSub: { fontSize: 9, fontFamily: "monospace", marginTop: 3 },

  section: { marginTop: 16 },
  sectionHead: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    paddingHorizontal: 16, marginBottom: 10,
  },
  sectionHeadLeft: { flexDirection: "row", alignItems: "center", gap: 8 },
  sectionAccent: { width: 3, height: 12, borderRadius: 2 },
  sectionTitle: { fontSize: 9, fontWeight: "700" as const, letterSpacing: 2 },
  sectionAction: { fontSize: 9, fontWeight: "600" as const, letterSpacing: 1 },

  emptyCard: { marginHorizontal: 16, borderRadius: 10, borderWidth: 1, padding: 20, gap: 6 },
  emptyLine1: { fontSize: 12, fontFamily: "monospace" },
  emptyLine2: { fontSize: 12 },
});
