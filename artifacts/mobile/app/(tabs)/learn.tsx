import { Feather } from "@expo/vector-icons";
import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Dimensions,
  FlatList,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { KeyboardAvoidingView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Svg, {
  Circle,
  Defs,
  Line,
  LinearGradient,
  Path,
  Rect,
  Stop,
  Text as SvgText,
} from "react-native-svg";

import { getApiBase, safeJson } from "@/constants/api";
import { useColors } from "@/hooks/useColors";

// ── Types ─────────────────────────────────────────────────────────────────────

interface LearnSession {
  id: string;
  role: "user" | "assistant";
  content: string;
  provider?: string;
  created_at: string;
}

interface ChartCandle {
  t: number; o: number; h: number; l: number; c: number; v: number;
}

interface MarketIndicators {
  current_price: number;
  price_change_pct: number;
  rsi: number;
  macd: number;
  macd_signal: number;
  macd_histogram: number;
  bb_upper: number;
  bb_middle: number;
  bb_lower: number;
  bb_pct: number;
  volume: number;
  volume_avg: number;
  ma20: number;
  market_condition: string;
}

interface MarketData {
  symbol: string;
  timeframe: string;
  indicators: MarketIndicators;
  chart: ChartCandle[];
}

interface LastAnswer {
  q: string;
  a: string;
  provider: string;
  topic: string;
  market_data?: MarketData | null;
}

// ── Preset learning topics ─────────────────────────────────────────────────

const TOPICS = [
  { icon: "trending-up",  label: "تحليل BTC",          topic: "تحليل Bitcoin الحالي وتوقعات السعر", color: "#F7931A" },
  { icon: "shield",       label: "تداول حلال",          topic: "مبادئ التداول الإسلامي الحلال وضوابطه الشرعية", color: "#10B981" },
  { icon: "activity",     label: "RSI & MACD",          topic: "شرح مؤشري RSI و MACD وكيفية استخدامهما في إشارات الدخول والخروج", color: "#6366F1" },
  { icon: "bar-chart-2",  label: "إدارة المخاطر",       topic: "أفضل استراتيجيات إدارة المخاطر في تداول العملات الرقمية", color: "#EF4444" },
  { icon: "zap",          label: "Scalping",             topic: "استراتيجية Scalping: متى تناسب السوق ومتى تتجنبها", color: "#F59E0B" },
  { icon: "layers",       label: "Mean Reversion",       topic: "استراتيجية Mean Reversion وكيف تعمل في أسواق التشفير", color: "#8B5CF6" },
  { icon: "globe",        label: "DeFi & DEX",           topic: "الفرق بين DEX و CEX وكيف يجعل DEX التداول أكثر حلالاً", color: "#4285F4" },
  { icon: "book-open",    label: "Bollinger Bands",      topic: "شرح Bollinger Bands واستخدامها لاكتشاف التقلبات", color: "#EC4899" },
  { icon: "cpu",          label: "تعلم الآلة",           topic: "كيف يستخدم البوت الذكاء الاصطناعي وتعلم الآلة لتحسين قراراته", color: "#10B981" },
  { icon: "dollar-sign",  label: "إدارة المحفظة",       topic: "أفضل طرق إدارة محفظة العملات الرقمية وتوزيع رأس المال", color: "#F59E0B" },
];

const PROVIDER_COLORS: Record<string, string> = {
  gemini:       "#4285F4",
  openai:       "#10A37F",
  claude:       "#C9642A",
  "rule-based": "#6B7280",
};

const CONDITION_MAP: Record<string, { label: string; color: string }> = {
  bullish:    { label: "صاعد ↑",      color: "#10B981" },
  bearish:    { label: "هابط ↓",      color: "#EF4444" },
  overbought: { label: "ذروة شراء ⚠", color: "#F59E0B" },
  oversold:   { label: "ذروة بيع 🔻", color: "#6366F1" },
  volatile:   { label: "متقلب ⚡",     color: "#F97316" },
  sideways:   { label: "جانبي ↔",     color: "#6B7280" },
};

function makeId() {
  return Date.now().toString() + Math.random().toString(36).slice(2, 7);
}

// ── Mini Price Line Chart ──────────────────────────────────────────────────────

const CHART_H = 72;
const PAD_L = 4; const PAD_R = 4; const PAD_T = 6; const PAD_B = 16;

function MiniPriceChart({ candles, color, width }: { candles: ChartCandle[]; color: string; width: number }) {
  if (!candles || candles.length < 4) return null;

  const w = width - PAD_L - PAD_R;
  const h = CHART_H - PAD_T - PAD_B;
  const prices = candles.map(c => c.c);
  const minP   = Math.min(...prices);
  const maxP   = Math.max(...prices);
  const range  = maxP - minP || 0.0001;

  const toX = (i: number) => PAD_L + (i / (prices.length - 1)) * w;
  const toY = (v: number) => PAD_T + h - ((v - minP) / range) * h;

  let pathD = "";
  let fillD = "";
  for (let i = 0; i < prices.length; i++) {
    const x = toX(i);
    const y = toY(prices[i]);
    if (i === 0) {
      pathD = `M ${x} ${y}`;
      fillD = `M ${x} ${CHART_H - PAD_B} L ${x} ${y}`;
    } else {
      const px = toX(i - 1);
      const py = toY(prices[i - 1]);
      const cpx1 = px + (x - px) / 3;
      const cpx2 = x - (x - px) / 3;
      pathD += ` C ${cpx1} ${py}, ${cpx2} ${y}, ${x} ${y}`;
      fillD += ` C ${cpx1} ${py}, ${cpx2} ${y}, ${x} ${y}`;
    }
  }
  fillD += ` L ${toX(prices.length - 1)} ${CHART_H - PAD_B} Z`;

  const finalPrice  = prices[prices.length - 1];
  const startPrice  = prices[0];
  const lineColor   = finalPrice >= startPrice ? color : "#EF4444";

  const lastX = toX(prices.length - 1);
  const lastY = toY(finalPrice);

  const labelCount = Math.min(4, prices.length);
  const labelIndices = Array.from({ length: labelCount }, (_, i) =>
    Math.round((i / (labelCount - 1)) * (prices.length - 1))
  );

  return (
    <Svg width={width} height={CHART_H}>
      <Defs>
        <LinearGradient id={`grad_${color.replace("#", "")}`} x1="0" y1="0" x2="0" y2="1">
          <Stop offset="0%" stopColor={lineColor} stopOpacity="0.35" />
          <Stop offset="100%" stopColor={lineColor} stopOpacity="0.02" />
        </LinearGradient>
      </Defs>
      <Path d={fillD} fill={`url(#grad_${color.replace("#", "")})`} />
      <Path d={pathD} stroke={lineColor} strokeWidth="1.8" fill="none" strokeLinecap="round" />
      <Circle cx={lastX} cy={lastY} r="3" fill={lineColor} stroke="#1a1a2e" strokeWidth="1.5" />
      {labelIndices.map(i => {
        const fmt = prices[i] >= 1000
          ? `$${(prices[i] / 1000).toFixed(1)}k`
          : `$${prices[i].toFixed(2)}`;
        return (
          <SvgText key={i} x={toX(i)} y={CHART_H - 3} fontSize="7" fill="#666" textAnchor="middle">
            {fmt}
          </SvgText>
        );
      })}
    </Svg>
  );
}

// ── RSI Gauge Bar ──────────────────────────────────────────────────────────────

function RSIGauge({ rsi, width }: { rsi: number; width: number }) {
  const pct      = Math.min(100, Math.max(0, rsi)) / 100;
  const color    = rsi > 70 ? "#F59E0B" : rsi < 30 ? "#6366F1" : "#10B981";
  const label    = rsi > 70 ? "ذروة شراء" : rsi < 30 ? "ذروة بيع" : "منطقة آمنة";
  const barW     = width - 8;
  const filledW  = barW * pct;

  return (
    <View style={{ gap: 4 }}>
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
        <Text style={{ fontSize: 10, color: "#999", fontWeight: "600" }}>RSI (14)</Text>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
          <Text style={{ fontSize: 11, color, fontWeight: "700" }}>{rsi.toFixed(1)}</Text>
          <Text style={{ fontSize: 9, color: "#777" }}>{label}</Text>
        </View>
      </View>
      <View style={{ height: 5, borderRadius: 3, backgroundColor: "#2a2a2a", width: barW }}>
        <View style={{ width: filledW, height: 5, borderRadius: 3, backgroundColor: color }} />
        {/* Overbought line at 70% */}
        <View style={{ position: "absolute", left: barW * 0.7 - 0.5, top: 0, width: 1, height: 5, backgroundColor: "#F59E0B44" }} />
        {/* Oversold line at 30% */}
        <View style={{ position: "absolute", left: barW * 0.3 - 0.5, top: 0, width: 1, height: 5, backgroundColor: "#6366F144" }} />
      </View>
    </View>
  );
}

// ── MACD Signal Badge ──────────────────────────────────────────────────────────

function MacdBadge({ macd, signal, histogram }: { macd: number; signal: number; histogram: number }) {
  const bullish = macd > signal;
  const color   = bullish ? "#10B981" : "#EF4444";
  const icon    = bullish ? "trending-up" : "trending-down";
  const label   = bullish ? "إشارة صعود" : "إشارة هبوط";

  return (
    <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
      <Text style={{ fontSize: 10, color: "#999", fontWeight: "600" }}>MACD</Text>
      <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
        <Feather name={icon as any} size={11} color={color} />
        <Text style={{ fontSize: 10, color, fontWeight: "700" }}>{label}</Text>
        <Text style={{ fontSize: 9, color: "#666" }}>({histogram >= 0 ? "+" : ""}{histogram.toFixed(5)})</Text>
      </View>
    </View>
  );
}

// ── Bollinger Band Position ────────────────────────────────────────────────────

function BBPosition({ bbPct, width }: { bbPct: number; width: number }) {
  const pct     = Math.min(1, Math.max(0, bbPct));
  const barW    = width - 8;
  const posX    = barW * pct;
  const color   = pct > 0.8 ? "#EF4444" : pct < 0.2 ? "#10B981" : "#6366F1";
  const label   = pct > 0.8 ? "قرب المقاومة" : pct < 0.2 ? "قرب الدعم" : "منتصف النطاق";

  return (
    <View style={{ gap: 4 }}>
      <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
        <Text style={{ fontSize: 10, color: "#999", fontWeight: "600" }}>Bollinger</Text>
        <Text style={{ fontSize: 10, color, fontWeight: "700" }}>{label}</Text>
      </View>
      <View style={{ height: 5, borderRadius: 3, backgroundColor: "#2a2a2a", width: barW }}>
        <View style={{ position: "absolute", left: Math.min(barW - 8, posX - 4), top: -1, width: 8, height: 7, borderRadius: 4, backgroundColor: color }} />
      </View>
    </View>
  );
}

// ── Volume Bar ─────────────────────────────────────────────────────────────────

function VolumeBar({ volume, volumeAvg, width }: { volume: number; volumeAvg: number; width: number }) {
  const ratio  = volumeAvg > 0 ? volume / volumeAvg : 1;
  const high   = ratio > 1.5;
  const color  = high ? "#F59E0B" : "#6B7280";
  const pct    = Math.min(1, ratio / 2);
  const barW   = width - 8;

  const fmt = (v: number) => v >= 1_000_000 ? `${(v / 1_000_000).toFixed(1)}M`
    : v >= 1_000 ? `${(v / 1_000).toFixed(0)}K` : v.toFixed(0);

  return (
    <View style={{ gap: 4 }}>
      <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
        <Text style={{ fontSize: 10, color: "#999", fontWeight: "600" }}>الحجم</Text>
        <Text style={{ fontSize: 10, color, fontWeight: "700" }}>
          {fmt(volume)} {high ? "⚡ نشاط مرتفع" : `(${(ratio * 100).toFixed(0)}% من المتوسط)`}
        </Text>
      </View>
      <View style={{ height: 5, borderRadius: 3, backgroundColor: "#2a2a2a", width: barW }}>
        <View style={{ width: barW * pct, height: 5, borderRadius: 3, backgroundColor: color }} />
      </View>
    </View>
  );
}

// ── Full Market Data Card ─────────────────────────────────────────────────────

function MarketDataCard({ data, colors }: { data: MarketData; colors: ReturnType<typeof useColors> }) {
  const screenW = Dimensions.get("window").width;
  const cardW   = screenW - 64;
  const sym     = data.symbol.replace("/USDT", "");
  const ind     = data.indicators;
  const change  = ind.price_change_pct;
  const cond    = CONDITION_MAP[ind.market_condition] ?? { label: ind.market_condition, color: "#6B7280" };
  const priceColor = change >= 0 ? "#10B981" : "#EF4444";

  return (
    <View style={[ss.marketCard, { backgroundColor: "#111", borderColor: "#2a2a2a" }]}>
      {/* Header row */}
      <View style={ss.mktHeader}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
          <View style={[ss.mktDot, { backgroundColor: cond.color }]} />
          <Text style={{ fontSize: 13, fontWeight: "700", color: "#fff" }}>{sym}/USDT</Text>
          <View style={[ss.mktCondBadge, { backgroundColor: `${cond.color}22` }]}>
            <Text style={{ fontSize: 9, color: cond.color, fontWeight: "700" }}>{cond.label}</Text>
          </View>
        </View>
        <View style={{ alignItems: "flex-end" }}>
          <Text style={{ fontSize: 14, fontWeight: "800", color: "#fff" }}>
            ${ind.current_price >= 1000
              ? ind.current_price.toLocaleString("en-US", { maximumFractionDigits: 2 })
              : ind.current_price.toFixed(4)}
          </Text>
          <Text style={{ fontSize: 11, fontWeight: "700", color: priceColor }}>
            {change >= 0 ? "+" : ""}{change.toFixed(3)}%
          </Text>
        </View>
      </View>

      {/* Mini Price Chart */}
      <View style={[ss.chartWrapper, { borderColor: "#222" }]}>
        <MiniPriceChart candles={data.chart} color={colors.primary} width={cardW - 16} />
        <Text style={ss.chartLabel}>آخر 15 ساعة — شمعة 15 دقيقة</Text>
      </View>

      {/* Indicators */}
      <View style={ss.indGrid}>
        <RSIGauge rsi={ind.rsi} width={cardW / 2 - 14} />
        <View style={ss.indDivider} />
        <BBPosition bbPct={ind.bb_pct} width={cardW / 2 - 14} />
      </View>

      <View style={[ss.indRow, { borderTopColor: "#222" }]}>
        <MacdBadge macd={ind.macd} signal={ind.macd_signal} histogram={ind.macd_histogram} />
      </View>

      <View style={[ss.indRow, { borderTopColor: "#222" }]}>
        <VolumeBar volume={ind.volume} volumeAvg={ind.volume_avg} width={cardW - 16} />
      </View>

      <Text style={ss.dataFooter}>📡 بيانات حية — MEXC Public API — {data.timeframe}</Text>
    </View>
  );
}

// ── Main Screen ───────────────────────────────────────────────────────────────

export default function LearnScreen() {
  const colors   = useColors();
  const insets   = useSafeAreaInsets();

  const topPad    = Platform.OS === "web" ? 67 : insets.top;
  const bottomPad = Platform.OS === "web" ? 90 : insets.bottom;

  const [sessions,    setSessions]    = useState<LearnSession[]>([]);
  const [loading,     setLoading]     = useState(false);
  const [histLoading, setHistLoading] = useState(true);
  const [customInput, setCustomInput] = useState("");
  const [activeTopic, setActiveTopic] = useState<string | null>(null);
  const [lastAnswer,  setLastAnswer]  = useState<LastAnswer | null>(null);

  const listRef = useRef<FlatList>(null);

  // ── Load recent learning sessions from DB ────────────────────────────────
  const loadSessions = useCallback(async () => {
    try {
      const r = await fetch(`${getApiBase()}/conversations?screen=learn&limit=40`);
      if (r.ok) {
        const d = await safeJson(r);
        if (d?.messages && d.messages.length > 0) {
          setSessions(
            d.messages.map((m: any) => ({
              id:         m.id ?? makeId(),
              role:       m.role as "user" | "assistant",
              content:    m.content,
              provider:   m.provider || undefined,
              created_at: m.created_at ?? new Date().toISOString(),
            }))
          );
        }
      }
    } catch { /* ignore */ }
    setHistLoading(false);
  }, []);

  useEffect(() => { loadSessions(); }, [loadSessions]);

  // ── Trigger learning session ──────────────────────────────────────────────
  const startLearn = async (topic: string, question?: string) => {
    if (loading) return;
    setActiveTopic(topic);
    setLoading(true);
    setLastAnswer(null);

    try {
      const res = await fetch(`${getApiBase()}/ai/learn`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ topic, question: question || topic }),
      });
      const data = await safeJson(res);
      if (data?.answer) {
        setLastAnswer({
          q:           data.question,
          a:           data.answer,
          provider:    data.provider ?? "rule-based",
          topic:       data.topic ?? topic,
          market_data: data.market_data ?? null,
        });
        setSessions((prev) => [
          { id: makeId(), role: "assistant", content: data.answer, provider: data.provider, created_at: new Date().toISOString() },
          { id: makeId(), role: "user",      content: data.question,                        created_at: new Date().toISOString() },
          ...prev,
        ]);
      }
    } catch {
      setLastAnswer({ q: topic, a: "⚠️ تعذر الاتصال بالخادم — تأكد من أن البوت يعمل", provider: "error", topic });
    } finally {
      setLoading(false);
      setActiveTopic(null);
    }
  };

  const handleCustomSend = () => {
    const q = customInput.trim();
    if (!q || loading) return;
    setCustomInput("");
    startLearn(q, q);
  };

  return (
    <KeyboardAvoidingView
      style={[ss.root, { backgroundColor: colors.background }]}
      behavior={Platform.OS === "ios" ? "padding" : "height"}
      keyboardVerticalOffset={0}
    >
      {/* ── Header ── */}
      <View style={[ss.header, { paddingTop: topPad + 8, backgroundColor: colors.background, borderBottomColor: colors.border }]}>
        <View>
          <Text style={[ss.title, { color: colors.foreground }]}>AI Learning Lab</Text>
          <Text style={[ss.subtitle, { color: colors.mutedForeground }]}>بيانات حية + تحليل Gemini في الوقت الفعلي</Text>
        </View>
        <View style={[ss.badge, { backgroundColor: `${colors.primary}18`, borderColor: `${colors.primary}44` }]}>
          <View style={[ss.badgeDot, { backgroundColor: colors.primary }]} />
          <Text style={[ss.badgeTxt, { color: colors.primary }]}>Live Data</Text>
        </View>
      </View>

      <FlatList
        ref={listRef}
        data={[]}
        renderItem={null}
        showsVerticalScrollIndicator={false}
        ListHeaderComponent={
          <View>

            {/* ── Current Answer Card ── */}
            {(loading || lastAnswer) && (
              <View style={[ss.answerCard, { backgroundColor: colors.card, borderColor: loading ? `${colors.primary}66` : colors.border }]}>
                <View style={ss.answerHeader}>
                  <View style={[ss.answerDot, { backgroundColor: loading ? colors.primary : (PROVIDER_COLORS[lastAnswer?.provider ?? ""] ?? colors.primary) }]} />
                  <Text style={[ss.answerTopic, { color: colors.primary }]} numberOfLines={1}>
                    {loading ? (activeTopic ?? "جاري السؤال...") : (lastAnswer?.topic ?? "")}
                  </Text>
                  {!loading && lastAnswer?.provider && lastAnswer.provider !== "rule-based" && (
                    <View style={[ss.provBadge, { backgroundColor: `${PROVIDER_COLORS[lastAnswer.provider] ?? colors.primary}22` }]}>
                      <Text style={[ss.provBadgeTxt, { color: PROVIDER_COLORS[lastAnswer.provider] ?? colors.primary }]}>
                        {lastAnswer.provider}
                      </Text>
                    </View>
                  )}
                </View>

                {loading ? (
                  <View style={ss.loadingRow}>
                    <ActivityIndicator size="small" color={colors.primary} />
                    <Text style={[ss.loadingTxt, { color: colors.mutedForeground }]}>Gemini يجلب البيانات ويحلل...</Text>
                  </View>
                ) : (
                  <>
                    {/* Question */}
                    <View style={[ss.questionBox, { backgroundColor: `${colors.primary}0E` }]}>
                      <Feather name="help-circle" size={11} color={colors.primary} />
                      <Text style={[ss.questionTxt, { color: colors.primary }]} numberOfLines={2}>{lastAnswer?.q}</Text>
                    </View>

                    {/* Market Data Card — shown only if available */}
                    {lastAnswer?.market_data && (
                      <MarketDataCard data={lastAnswer.market_data} colors={colors} />
                    )}

                    {/* AI Answer */}
                    <Text style={[ss.answerTxt, { color: colors.foreground }]}>{lastAnswer?.a}</Text>
                  </>
                )}
              </View>
            )}

            {/* ── Topics Grid ── */}
            <View style={ss.sectionHeader}>
              <Feather name="book-open" size={13} color={colors.primary} />
              <Text style={[ss.sectionTitle, { color: colors.foreground }]}>اختر موضوعاً للتعلم</Text>
            </View>

            <View style={ss.topicsGrid}>
              {TOPICS.map((t) => {
                const isActive = activeTopic === t.topic && loading;
                return (
                  <Pressable
                    key={t.topic}
                    style={[ss.topicCard, {
                      backgroundColor: isActive ? `${t.color}22` : colors.card,
                      borderColor:     isActive ? `${t.color}88` : colors.border,
                    }]}
                    onPress={() => startLearn(t.topic)}
                    disabled={loading}
                  >
                    <View style={[ss.topicIcon, { backgroundColor: `${t.color}18` }]}>
                      {isActive
                        ? <ActivityIndicator size="small" color={t.color} />
                        : <Feather name={t.icon as any} size={14} color={t.color} />
                      }
                    </View>
                    <Text style={[ss.topicLabel, { color: colors.foreground }]} numberOfLines={2}>
                      {t.label}
                    </Text>
                  </Pressable>
                );
              })}
            </View>

            {/* ── Recent Sessions ── */}
            {sessions.length > 0 && (
              <>
                <View style={ss.sectionHeader}>
                  <Feather name="clock" size={13} color={colors.mutedForeground} />
                  <Text style={[ss.sectionTitle, { color: colors.foreground }]}>جلسات التعلم السابقة</Text>
                </View>

                {histLoading ? (
                  <ActivityIndicator size="small" color={colors.primary} style={{ marginVertical: 16 }} />
                ) : (
                  sessions.slice(0, 20).map((s, i) => {
                    const isUser  = s.role === "user";
                    const provCol = PROVIDER_COLORS[s.provider ?? ""] ?? colors.primary;
                    return (
                      <View
                        key={s.id ?? i}
                        style={[
                          ss.sessionRow,
                          isUser
                            ? [ss.sessionUser, { backgroundColor: `${colors.primary}12`, borderColor: `${colors.primary}33` }]
                            : [ss.sessionBot,  { backgroundColor: colors.card, borderColor: colors.border }],
                        ]}
                      >
                        <View style={ss.sessionRoleRow}>
                          <View style={[ss.sessionDot, { backgroundColor: isUser ? colors.primary : provCol }]} />
                          <Text style={[ss.sessionRole, { color: isUser ? colors.primary : provCol }]}>
                            {isUser ? "السؤال" : (s.provider && s.provider !== "rule-based" ? s.provider : "الإجابة")}
                          </Text>
                          <Text style={[ss.sessionTime, { color: colors.mutedForeground }]}>
                            {new Date(s.created_at).toLocaleDateString("ar-DZ")}
                          </Text>
                        </View>
                        <Text style={[ss.sessionContent, { color: colors.foreground }]} numberOfLines={isUser ? 2 : 6}>
                          {s.content}
                        </Text>
                      </View>
                    );
                  })
                )}
              </>
            )}

            {!histLoading && sessions.length === 0 && !lastAnswer && (
              <View style={ss.emptyBox}>
                <Feather name="bar-chart-2" size={32} color={colors.mutedForeground} />
                <Text style={[ss.emptyTxt, { color: colors.foreground }]}>لم تبدأ أي جلسة تعلم بعد</Text>
                <Text style={[ss.emptySub, { color: colors.mutedForeground }]}>اختر موضوعاً وسيجلب البوت بيانات السوق الحية ويسأل Gemini!</Text>
              </View>
            )}

            <View style={{ height: 16 }} />
          </View>
        }
        keyExtractor={() => "static"}
      />

      {/* ── Custom Question Input ── */}
      <View style={[ss.inputRow, { backgroundColor: colors.background, borderTopColor: colors.border, paddingBottom: bottomPad + 8 }]}>
        <TextInput
          style={[ss.input, { backgroundColor: colors.card, color: colors.foreground, borderColor: colors.border }]}
          placeholder="اكتب سؤالاً مخصصاً... (سيجلب البوت البيانات الحية)"
          placeholderTextColor={colors.mutedForeground}
          value={customInput}
          onChangeText={setCustomInput}
          returnKeyType="send"
          blurOnSubmit
          onSubmitEditing={handleCustomSend}
          editable={!loading}
        />
        <Pressable
          onPress={handleCustomSend}
          disabled={!customInput.trim() || loading}
          style={[ss.sendBtn, {
            backgroundColor: customInput.trim() && !loading ? colors.primary : colors.muted,
          }]}
        >
          {loading
            ? <ActivityIndicator size="small" color={colors.primary} />
            : <Feather name="send" size={16} color={customInput.trim() && !loading ? "#fff" : colors.mutedForeground} />
          }
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const ss = StyleSheet.create({
  root:           { flex: 1 },

  header:         { paddingHorizontal: 20, paddingBottom: 14, borderBottomWidth: 1, flexDirection: "row", alignItems: "flex-end", justifyContent: "space-between" },
  title:          { fontSize: 22, fontWeight: "700", letterSpacing: -0.5 },
  subtitle:       { fontSize: 11, marginTop: 2 },
  badge:          { flexDirection: "row", alignItems: "center", gap: 5, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 10, borderWidth: 1 },
  badgeDot:       { width: 6, height: 6, borderRadius: 3 },
  badgeTxt:       { fontSize: 12, fontWeight: "700" },

  answerCard:     { margin: 16, borderRadius: 14, borderWidth: 1.5, padding: 14, gap: 10 },
  answerHeader:   { flexDirection: "row", alignItems: "center", gap: 8 },
  answerDot:      { width: 8, height: 8, borderRadius: 4 },
  answerTopic:    { flex: 1, fontSize: 12, fontWeight: "700" },
  provBadge:      { paddingHorizontal: 7, paddingVertical: 3, borderRadius: 7 },
  provBadgeTxt:   { fontSize: 10, fontWeight: "700" },
  loadingRow:     { flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 8 },
  loadingTxt:     { fontSize: 13 },
  questionBox:    { flexDirection: "row", alignItems: "flex-start", gap: 6, padding: 8, borderRadius: 8 },
  questionTxt:    { flex: 1, fontSize: 12, fontWeight: "600", lineHeight: 17 },
  answerTxt:      { fontSize: 13, lineHeight: 21 },

  // Market Data Card
  marketCard:     { borderRadius: 12, borderWidth: 1, padding: 10, gap: 10, marginTop: 4 },
  mktHeader:      { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between" },
  mktDot:         { width: 7, height: 7, borderRadius: 3.5, marginTop: 3 },
  mktCondBadge:   { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 },
  chartWrapper:   { borderRadius: 8, borderWidth: 1, overflow: "hidden", paddingBottom: 2 },
  chartLabel:     { fontSize: 8, color: "#555", textAlign: "center", paddingBottom: 4 },
  indGrid:        { flexDirection: "row", gap: 8 },
  indDivider:     { width: 1, backgroundColor: "#222", marginVertical: 2 },
  indRow:         { borderTopWidth: 1, paddingTop: 8 },
  dataFooter:     { fontSize: 8, color: "#444", textAlign: "center", paddingTop: 2 },

  sectionHeader:  { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 16, paddingTop: 16, paddingBottom: 8 },
  sectionTitle:   { fontSize: 13, fontWeight: "700" },

  topicsGrid:     { flexDirection: "row", flexWrap: "wrap", paddingHorizontal: 12, gap: 8, paddingBottom: 8 },
  topicCard:      { width: "47%", flexGrow: 1, flexDirection: "row", alignItems: "center", gap: 8, padding: 12, borderRadius: 12, borderWidth: 1 },
  topicIcon:      { width: 30, height: 30, borderRadius: 9, alignItems: "center", justifyContent: "center" },
  topicLabel:     { flex: 1, fontSize: 12, fontWeight: "600", lineHeight: 17 },

  sessionRow:     { marginHorizontal: 16, marginBottom: 6, borderRadius: 10, borderWidth: 1, padding: 10 },
  sessionUser:    {},
  sessionBot:     {},
  sessionRoleRow: { flexDirection: "row", alignItems: "center", gap: 6, marginBottom: 5 },
  sessionDot:     { width: 6, height: 6, borderRadius: 3 },
  sessionRole:    { fontSize: 10, fontWeight: "700", flex: 1 },
  sessionTime:    { fontSize: 9 },
  sessionContent: { fontSize: 12, lineHeight: 18 },

  emptyBox:       { alignItems: "center", gap: 8, paddingVertical: 40, paddingHorizontal: 32 },
  emptyTxt:       { fontSize: 15, fontWeight: "700", textAlign: "center" },
  emptySub:       { fontSize: 12, textAlign: "center", lineHeight: 19 },

  inputRow:       { flexDirection: "row", alignItems: "flex-end", gap: 10, paddingHorizontal: 16, paddingTop: 10, borderTopWidth: 1 },
  input:          { flex: 1, borderRadius: 20, borderWidth: 1, paddingHorizontal: 16, paddingVertical: 10, fontSize: 14, maxHeight: 80 },
  sendBtn:        { width: 42, height: 42, borderRadius: 21, alignItems: "center", justifyContent: "center" },
});
