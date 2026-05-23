/**
 * شاشة التحليلات — Analytics Screen
 * رسم بياني تراكمي PnL، أعمدة يومية، سلاسل الفوز/الخسارة،
 * أفضل/أسوأ الصفقات، الأداء حسب العملة
 */
import { Feather } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Platform,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
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

interface BacktestResult {
  success: boolean;
  symbol: string;
  days: number;
  total_trades: number;
  wins: number;
  losses: number;
  win_rate: number;
  total_pnl_usd: number;
  total_pnl_pct: number;
  max_drawdown_pct: number;
  profit_factor: number;
  sharpe_ratio: number;
  avg_win_usd: number;
  avg_loss_usd: number;
  avg_duration_hours: number;
  initial_capital: number;
  final_capital: number;
  equity_curve: number[];
  message?: string;
  error?: string;
}

interface ZakatData {
  zakat_calculation: {
    total_profit_usd: number;
    total_loss_usd: number;
    net_pnl_usd: number;
    nisab_usd: number;
    above_nisab: boolean;
    zakat_rate_pct: number;
    zakat_due_usd: number;
    remaining_after_zakat: number;
  };
  status: string;
  status_ar: string;
  total_trades: number;
  total_wins: number;
  monthly_profits: { month: string; profit: number; loss: number; trades: number }[];
  notes: string[];
}

interface PortfolioAsset {
  symbol: string;
  allocation_pct: number;
  enabled: boolean;
}

interface DailyPoint { date: string; pnl: number; wins: number; losses: number; trades: number }
interface CumPoint   { date: string; cumPnl: number }
interface SymStat    { symbol: string; trades: number; wins: number; pnl: number; win_rate: number }
interface TradeStat  { symbol: string; pnl: number; pnl_percent: number; side: string; closed_at: string }
interface ChartData {
  daily: DailyPoint[];
  cumulative: CumPoint[];
  streak: { current_type: string; current_count: number; best_win: number; best_loss: number };
  top_trades: TradeStat[];
  bottom_trades: TradeStat[];
  by_symbol: SymStat[];
  summary: {
    total_pnl: number; roi_percent: number; total_trades: number;
    wins: number; losses: number; win_rate: number;
    profit_factor: number; avg_win: number; avg_loss: number;
  };
}

type Range = "7" | "30" | "0";
const RANGES: { key: Range; label: string }[] = [
  { key: "7",  label: "7 أيام" },
  { key: "30", label: "شهر" },
  { key: "0",  label: "الكل" },
];

const CHART_H    = 160;
const BAR_CHART_H = 90;
const PAD_L = 8;
const PAD_R = 8;
const PAD_T = 12;
const PAD_B = 24;

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(v: number, digits = 4) {
  const abs = Math.abs(v);
  if (abs === 0) return "$0.00";
  if (abs >= 1000) return `$${(v / 1000).toFixed(2)}k`;
  return `${v >= 0 ? "+" : ""}$${v.toFixed(digits)}`;
}

function shortDate(d: string) {
  if (!d) return "";
  const parts = d.split("-");
  if (parts.length < 3) return d;
  return `${parts[2]}/${parts[1]}`;
}

// ── SVG Line Chart ────────────────────────────────────────────────────────────

function LineChart({ data, width, primaryColor }: { data: CumPoint[]; width: number; primaryColor: string }) {
  if (!data || data.length < 2) {
    return (
      <View style={{ height: CHART_H, alignItems: "center", justifyContent: "center" }}>
        <Feather name="bar-chart-2" size={28} color="#555" />
        <Text style={{ color: "#666", fontSize: 11, marginTop: 6 }}>لا توجد بيانات كافية بعد</Text>
      </View>
    );
  }

  const w = width - PAD_L - PAD_R;
  const h = CHART_H - PAD_T - PAD_B;

  const values = data.map(d => d.cumPnl);
  const minVal = Math.min(0, ...values);
  const maxVal = Math.max(0, ...values);
  const range  = maxVal - minVal || 0.0001;

  const toX = (i: number) => PAD_L + (i / (data.length - 1)) * w;
  const toY = (v: number) => PAD_T + h - ((v - minVal) / range) * h;
  const zeroY = toY(0);

  // Build smooth path using cubic bezier
  let pathD = "";
  let fillD = "";
  for (let i = 0; i < data.length; i++) {
    const x = toX(i);
    const y = toY(data[i].cumPnl);
    if (i === 0) {
      pathD = `M ${x} ${y}`;
      fillD = `M ${x} ${zeroY} L ${x} ${y}`;
    } else {
      const px = toX(i - 1);
      const py = toY(data[i - 1].cumPnl);
      const cpx1 = px + (x - px) / 3;
      const cpx2 = x - (x - px) / 3;
      pathD += ` C ${cpx1} ${py}, ${cpx2} ${y}, ${x} ${y}`;
      fillD += ` C ${cpx1} ${py}, ${cpx2} ${y}, ${x} ${y}`;
    }
  }
  fillD += ` L ${toX(data.length - 1)} ${zeroY} Z`;

  // X-axis labels (up to 6 evenly spaced)
  const labelCount = Math.min(6, data.length);
  const labelIndices = Array.from({ length: labelCount }, (_, i) =>
    Math.round((i / (labelCount - 1)) * (data.length - 1))
  );

  const finalPnl = values[values.length - 1];
  const lineColor = finalPnl >= 0 ? primaryColor : "#FF6B6B";

  return (
    <Svg width={width} height={CHART_H}>
      <Defs>
        <LinearGradient id="fillGrad" x1="0" y1="0" x2="0" y2="1">
          <Stop offset="0%" stopColor={lineColor} stopOpacity="0.28" />
          <Stop offset="100%" stopColor={lineColor} stopOpacity="0.02" />
        </LinearGradient>
      </Defs>

      {/* Zero line */}
      <Line
        x1={PAD_L} y1={zeroY} x2={PAD_L + w} y2={zeroY}
        stroke="#444" strokeWidth="0.8" strokeDasharray="4,3"
      />

      {/* Gradient fill */}
      <Path d={fillD} fill="url(#fillGrad)" />

      {/* Main line */}
      <Path d={pathD} stroke={lineColor} strokeWidth="2.2" fill="none" strokeLinecap="round" />

      {/* Last point dot */}
      <Circle
        cx={toX(data.length - 1)}
        cy={toY(finalPnl)}
        r="4" fill={lineColor} stroke="#1a1a2e" strokeWidth="2"
      />

      {/* X-axis labels */}
      {labelIndices.map(i => (
        <SvgText
          key={i}
          x={toX(i)} y={CHART_H - 4}
          fontSize="8" fill="#666" textAnchor="middle"
        >
          {shortDate(data[i].date)}
        </SvgText>
      ))}
    </Svg>
  );
}

// ── SVG Bar Chart ─────────────────────────────────────────────────────────────

function BarChart({ data, width, primaryColor }: { data: DailyPoint[]; width: number; primaryColor: string }) {
  if (!data || data.length === 0) return null;

  const w = width - PAD_L - PAD_R;
  const h = BAR_CHART_H - PAD_T - PAD_B + 10;

  const values = data.map(d => d.pnl);
  const maxAbs = Math.max(0.0001, ...values.map(Math.abs));

  const barW = Math.max(3, w / data.length - 2);
  const midY = PAD_T + h / 2;

  return (
    <Svg width={width} height={BAR_CHART_H}>
      {/* Zero line */}
      <Line x1={PAD_L} y1={midY} x2={PAD_L + w} y2={midY} stroke="#444" strokeWidth="0.8" />

      {data.map((d, i) => {
        const x = PAD_L + (i / data.length) * w + (w / data.length - barW) / 2;
        const barH = Math.max(2, (Math.abs(d.pnl) / maxAbs) * (h / 2 - 2));
        const y = d.pnl >= 0 ? midY - barH : midY;
        const color = d.pnl >= 0 ? primaryColor : "#FF6B6B";
        return <Rect key={i} x={x} y={y} width={barW} height={barH} fill={color} rx="1.5" opacity="0.85" />;
      })}
    </Svg>
  );
}

// ── Stat Card ─────────────────────────────────────────────────────────────────

function StatCard({ label, value, sub, color, icon }: { label: string; value: string; sub?: string; color: string; icon: string }) {
  const colors = useColors();
  return (
    <View style={[sc.card, { backgroundColor: `${color}0E`, borderColor: `${color}28` }]}>
      <View style={[sc.iconBox, { backgroundColor: `${color}1A` }]}>
        <Feather name={icon as any} size={13} color={color} />
      </View>
      <Text style={[sc.val, { color }]}>{value}</Text>
      <Text style={[sc.label, { color: colors.mutedForeground }]}>{label}</Text>
      {sub ? <Text style={[sc.sub, { color: colors.mutedForeground }]}>{sub}</Text> : null}
    </View>
  );
}
const sc = StyleSheet.create({
  card:    { flex: 1, padding: 10, borderRadius: 12, borderWidth: 1, gap: 3 },
  iconBox: { width: 26, height: 26, borderRadius: 7, alignItems: "center", justifyContent: "center", marginBottom: 2 },
  val:     { fontSize: 16, fontWeight: "800" as const, letterSpacing: -0.5 },
  label:   { fontSize: 9, fontWeight: "700" as const, letterSpacing: 0.5 },
  sub:     { fontSize: 9, marginTop: 1 },
});

// ── Streak Badge ──────────────────────────────────────────────────────────────

function StreakBadge({ type, count, label, color }: { type: string; count: number; label: string; color: string }) {
  const colors = useColors();
  const dots = Array.from({ length: Math.min(count, 10) });
  return (
    <View style={[sb.wrap, { borderColor: `${color}33`, backgroundColor: `${color}0A` }]}>
      <View style={sb.top}>
        <View style={[sb.dot, { backgroundColor: color }]} />
        <Text style={[sb.label, { color: colors.mutedForeground }]}>{label}</Text>
        <Text style={[sb.count, { color }]}>{count} متتالية</Text>
      </View>
      <View style={sb.dots}>
        {dots.map((_, i) => (
          <View key={i} style={[sb.pip, { backgroundColor: color }]} />
        ))}
        {count > 10 && <Text style={[sb.more, { color }]}>+{count - 10}</Text>}
      </View>
    </View>
  );
}
const sb = StyleSheet.create({
  wrap:  { flex: 1, padding: 10, borderRadius: 12, borderWidth: 1, gap: 6 },
  top:   { flexDirection: "row" as const, alignItems: "center" as const, gap: 6 },
  dot:   { width: 6, height: 6, borderRadius: 3 },
  label: { flex: 1, fontSize: 10, fontWeight: "700" as const },
  count: { fontSize: 13, fontWeight: "800" as const },
  dots:  { flexDirection: "row" as const, flexWrap: "wrap" as const, gap: 3, alignItems: "center" as const },
  pip:   { width: 8, height: 8, borderRadius: 4 },
  more:  { fontSize: 10, fontWeight: "700" as const },
});

// ── Trade Row ─────────────────────────────────────────────────────────────────

function TradeRow({ trade, isTop }: { trade: TradeStat; isTop: boolean }) {
  const colors = useColors();
  const pnl = trade.pnl ?? 0;
  const pct = trade.pnl_percent ?? 0;
  const color = pnl >= 0 ? colors.primary : "#FF6B6B";
  const sym = (trade.symbol || "???").replace("/USDT", "").replace("-USDT", "");
  return (
    <View style={[tr.row, { borderBottomColor: colors.border }]}>
      <View style={[tr.badge, { backgroundColor: `${color}18` }]}>
        <Text style={[tr.sym, { color }]}>{sym}</Text>
      </View>
      <View style={{ flex: 1, paddingHorizontal: 10 }}>
        <Text style={[tr.side, { color: colors.mutedForeground }]}>
          {trade.side === "buy" ? "شراء" : "بيع"} • {trade.closed_at?.slice(0, 10) ?? "—"}
        </Text>
      </View>
      <View style={{ alignItems: "flex-end" as const }}>
        <Text style={[tr.pnl, { color }]}>{fmt(pnl)}</Text>
        <Text style={[tr.pct, { color }]}>{pct >= 0 ? "+" : ""}{pct.toFixed(2)}%</Text>
      </View>
    </View>
  );
}
const tr = StyleSheet.create({
  row:   { flexDirection: "row" as const, alignItems: "center" as const, paddingVertical: 10, borderBottomWidth: 1 },
  badge: { width: 40, height: 26, borderRadius: 6, alignItems: "center" as const, justifyContent: "center" as const },
  sym:   { fontSize: 10, fontWeight: "800" as const },
  side:  { fontSize: 10 },
  pnl:   { fontSize: 13, fontWeight: "700" as const },
  pct:   { fontSize: 10, marginTop: 1 },
});

// ── Symbol Bar ────────────────────────────────────────────────────────────────

function SymbolBar({ sym, max, primaryColor }: { sym: SymStat; max: number; primaryColor: string }) {
  const colors = useColors();
  const color = sym.pnl >= 0 ? primaryColor : "#FF6B6B";
  const pct = max > 0 ? Math.abs(sym.pnl) / max : 0;
  return (
    <View style={[symb.row, { borderBottomColor: colors.border }]}>
      <Text style={[symb.sym, { color: colors.foreground }]}>{sym.symbol}</Text>
      <View style={symb.barWrap}>
        <View style={[symb.bar, { width: `${Math.max(4, pct * 100)}%`, backgroundColor: color }]} />
      </View>
      <Text style={[symb.wr, { color: colors.mutedForeground }]}>{sym.win_rate.toFixed(0)}%</Text>
      <Text style={[symb.pnl, { color }]}>{fmt(sym.pnl, 3)}</Text>
    </View>
  );
}
const symb = StyleSheet.create({
  row:     { flexDirection: "row" as const, alignItems: "center" as const, paddingVertical: 8, gap: 8, borderBottomWidth: 1 },
  sym:     { width: 36, fontSize: 11, fontWeight: "700" as const },
  barWrap: { flex: 1, height: 8, backgroundColor: "#1a1a2e", borderRadius: 4, overflow: "hidden" as const },
  bar:     { height: 8, borderRadius: 4 },
  wr:      { width: 30, fontSize: 10, textAlign: "right" as const },
  pnl:     { width: 58, fontSize: 11, fontWeight: "700" as const, textAlign: "right" as const },
});

// ── Equity Mini Chart ─────────────────────────────────────────────────────────

function EquityMiniChart({ data, color, width = 240 }: { data: number[]; color: string; width?: number }) {
  if (!data || data.length < 2) return null;
  const h = 48;
  const pad = 4;
  const w = width - pad * 2;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const toX = (i: number) => pad + (i / (data.length - 1)) * w;
  const toY = (v: number) => pad + h - ((v - min) / range) * (h - pad * 2);
  let path = `M ${toX(0)} ${toY(data[0])}`;
  for (let i = 1; i < data.length; i++) {
    path += ` L ${toX(i)} ${toY(data[i])}`;
  }
  const fillPath = path + ` L ${toX(data.length - 1)} ${h + pad} L ${pad} ${h + pad} Z`;
  const finalColor = data[data.length - 1] >= data[0] ? color : "#FF6B6B";
  return (
    <Svg width={width} height={h + pad * 2}>
      <Defs>
        <LinearGradient id="eq" x1="0" y1="0" x2="0" y2="1">
          <Stop offset="0%" stopColor={finalColor} stopOpacity="0.3" />
          <Stop offset="100%" stopColor={finalColor} stopOpacity="0.02" />
        </LinearGradient>
      </Defs>
      <Path d={fillPath} fill="url(#eq)" />
      <Path d={path} stroke={finalColor} strokeWidth="2" fill="none" strokeLinecap="round" />
    </Svg>
  );
}

// ── Backtest Panel ────────────────────────────────────────────────────────────

const BT_SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "ADA/USDT", "AVAX/USDT", "LTC/USDT"];
const BT_DAYS    = [7, 14, 30, 60, 90];

function BacktestPanel({ colors }: { colors: any }) {
  const [symbol, setSymbol]   = useState("BTC/USDT");
  const [days, setDays]       = useState(30);
  const [loading, setLoading] = useState(false);
  const [result, setResult]   = useState<BacktestResult | null>(null);
  const [chartW, setChartW]   = useState(280);

  const run = async () => {
    setLoading(true);
    setResult(null);
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    try {
      const res = await fetch(`${getApiBase()}/backtest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol, days, initial_capital: 10000, interval: "15m" }),
      });
      if (res.ok) setResult(await safeJson(res));
    } catch { /* ignore */ }
    finally { setLoading(false); }
  };

  const r = result;
  const pnlColor = (r?.total_pnl_usd ?? 0) >= 0 ? colors.primary : "#FF6B6B";

  return (
    <View style={[btp.card, { backgroundColor: colors.card, borderColor: colors.border }]}>
      <SectionTitle icon="rewind" title="اختبار الاستراتيجية 🧪" colors={colors} />

      {/* Symbol selector */}
      <View style={btp.row}>
        <Text style={[btp.lbl, { color: colors.mutedForeground }]}>العملة</Text>
        <View style={btp.chipsWrap}>
          {BT_SYMBOLS.map(s => (
            <Pressable
              key={s}
              onPress={() => { setSymbol(s); setResult(null); }}
              style={[btp.chip, { borderColor: symbol === s ? colors.primary : colors.border,
                backgroundColor: symbol === s ? `${colors.primary}18` : colors.background }]}
            >
              <Text style={[btp.chipTxt, { color: symbol === s ? colors.primary : colors.mutedForeground }]}>
                {s.replace("/USDT", "")}
              </Text>
            </Pressable>
          ))}
        </View>
      </View>

      {/* Days selector */}
      <View style={btp.row}>
        <Text style={[btp.lbl, { color: colors.mutedForeground }]}>الفترة</Text>
        <View style={btp.chips}>
          {BT_DAYS.map(d => (
            <Pressable
              key={d}
              onPress={() => { setDays(d); setResult(null); }}
              style={[btp.chip, { borderColor: days === d ? colors.primary : colors.border,
                backgroundColor: days === d ? `${colors.primary}18` : colors.background }]}
            >
              <Text style={[btp.chipTxt, { color: days === d ? colors.primary : colors.mutedForeground }]}>
                {d}ي
              </Text>
            </Pressable>
          ))}
        </View>
      </View>

      {/* Run button */}
      <TouchableOpacity
        onPress={run}
        disabled={loading}
        style={[btp.runBtn, { backgroundColor: loading ? `${colors.primary}44` : colors.primary }]}
      >
        {loading ? (
          <ActivityIndicator color="#fff" size="small" />
        ) : (
          <>
            <Feather name="play" size={13} color="#fff" />
            <Text style={btp.runTxt}>تشغيل الاختبار</Text>
          </>
        )}
      </TouchableOpacity>

      {/* Results */}
      {r && (
        <View style={btp.results}>
          {r.error ? (
            <Text style={[btp.error, { color: "#FF6B6B" }]}>{r.error}</Text>
          ) : r.total_trades === 0 ? (
            <Text style={[btp.error, { color: colors.mutedForeground }]}>{r.message ?? "لا توجد إشارات في هذه الفترة"}</Text>
          ) : (
            <>
              {/* PnL headline */}
              <View style={btp.headline}>
                <View>
                  <Text style={[btp.pnlBig, { color: pnlColor }]}>
                    {r.total_pnl_usd >= 0 ? "+" : ""}{r.total_pnl_usd.toFixed(2)} USDT
                  </Text>
                  <Text style={[btp.pnlPct, { color: pnlColor }]}>
                    {r.total_pnl_pct >= 0 ? "+" : ""}{r.total_pnl_pct.toFixed(2)}%
                  </Text>
                </View>
                <View style={btp.headRight}>
                  <Text style={[btp.statLbl, { color: colors.mutedForeground }]}>نسبة فوز</Text>
                  <Text style={[btp.statVal, { color: colors.foreground }]}>{r.win_rate.toFixed(1)}%</Text>
                  <Text style={[btp.statSub, { color: colors.mutedForeground }]}>{r.wins}ر/{r.losses}خ</Text>
                </View>
              </View>

              {/* Stats grid */}
              <View style={btp.statsGrid}>
                {[
                  { l: "صفقات", v: `${r.total_trades}` },
                  { l: "Profit Factor", v: r.profit_factor >= 99 ? "∞" : `${r.profit_factor}x` },
                  { l: "Max Drawdown", v: `-${r.max_drawdown_pct.toFixed(1)}%`, c: "#FF6B6B" },
                  { l: "Sharpe", v: `${r.sharpe_ratio.toFixed(2)}` },
                  { l: "متوسط ربح", v: `+$${r.avg_win_usd.toFixed(2)}`, c: colors.primary },
                  { l: "متوسط خسارة", v: `$${r.avg_loss_usd.toFixed(2)}`, c: "#FF6B6B" },
                ].map((item, i) => (
                  <View key={i} style={[btp.statCell, { borderColor: colors.border }]}>
                    <Text style={[btp.cellLbl, { color: colors.mutedForeground }]}>{item.l}</Text>
                    <Text style={[btp.cellVal, { color: item.c ?? colors.foreground }]}>{item.v}</Text>
                  </View>
                ))}
              </View>

              {/* Equity curve */}
              {(r.equity_curve?.length ?? 0) > 3 && (
                <View onLayout={e => setChartW(e.nativeEvent.layout.width - 4)}>
                  <Text style={[btp.cellLbl, { color: colors.mutedForeground, marginBottom: 6, marginTop: 4 }]}>
                    منحنى رأس المال
                  </Text>
                  <EquityMiniChart data={r.equity_curve} color={colors.primary} width={chartW} />
                </View>
              )}

              <Text style={[btp.note, { color: colors.mutedForeground }]}>
                رأس المال الأولي ${r.initial_capital.toLocaleString()} → ${r.final_capital.toLocaleString()} | {r.days} يوم
              </Text>
            </>
          )}
        </View>
      )}
    </View>
  );
}
const btp = StyleSheet.create({
  card:      { borderRadius: 16, borderWidth: 1, padding: 14, gap: 10 },
  row:       { gap: 6 },
  lbl:       { fontSize: 10, fontWeight: "700" as const, letterSpacing: 0.8 },
  chips:     { flexDirection: "row" as const, gap: 6, flexWrap: "wrap" as const },
  chipsWrap: { flexDirection: "row" as const, gap: 6, flexWrap: "wrap" as const },
  chip:      { paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8, borderWidth: 1 },
  chipTxt:   { fontSize: 11, fontWeight: "600" as const },
  runBtn:    { borderRadius: 10, padding: 12, alignItems: "center" as const, flexDirection: "row" as const, justifyContent: "center" as const, gap: 8 },
  runTxt:    { color: "#fff", fontSize: 13, fontWeight: "700" as const },
  results:   { gap: 10, paddingTop: 4 },
  error:     { fontSize: 12, textAlign: "center" as const, padding: 16 },
  headline:  { flexDirection: "row" as const, justifyContent: "space-between" as const, alignItems: "flex-start" as const },
  headRight: { alignItems: "flex-end" as const, gap: 2 },
  pnlBig:    { fontSize: 24, fontWeight: "800" as const, fontFamily: "monospace" },
  pnlPct:    { fontSize: 13, fontWeight: "600" as const, fontFamily: "monospace" },
  statLbl:   { fontSize: 8, letterSpacing: 1, fontWeight: "700" as const },
  statVal:   { fontSize: 16, fontWeight: "700" as const, fontFamily: "monospace" },
  statSub:   { fontSize: 10 },
  statsGrid: { flexDirection: "row" as const, flexWrap: "wrap" as const, gap: 6 },
  statCell:  { flex: 1, minWidth: "30%", borderWidth: 1, borderRadius: 8, padding: 8, gap: 3 },
  cellLbl:   { fontSize: 9, letterSpacing: 0.5 },
  cellVal:   { fontSize: 13, fontWeight: "700" as const, fontFamily: "monospace" },
  note:      { fontSize: 9, textAlign: "center" as const, fontFamily: "monospace" },
});

// ── Zakat Panel ───────────────────────────────────────────────────────────────

function ZakatPanel({ colors }: { colors: any }) {
  const [data, setData]       = useState<ZakatData | null>(null);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded]   = useState(false);

  const load = async () => {
    if (loading) return;
    setLoading(true);
    try {
      const res = await fetch(`${getApiBase()}/zakat`);
      if (res.ok) setData(await safeJson(res));
    } catch { /* ignore */ }
    finally { setLoading(false); setLoaded(true); }
  };

  const zk = data?.zakat_calculation;
  const statusColor = data?.status === "zakat_due" ? "#F59E0B" :
                      data?.status === "below_nisab" ? colors.primary : colors.mutedForeground;

  return (
    <View style={[zkp.card, { backgroundColor: colors.card, borderColor: data?.status === "zakat_due" ? "#F59E0B44" : colors.border }]}>
      <View style={zkp.header}>
        <SectionTitle icon="moon" title="حاسبة الزكاة ☪️" colors={colors} />
        {!loaded && (
          <Pressable onPress={load} style={[zkp.loadBtn, { borderColor: colors.primary, backgroundColor: `${colors.primary}15` }]}>
            <Text style={[zkp.loadTxt, { color: colors.primary }]}>احسب</Text>
          </Pressable>
        )}
        {loaded && (
          <Pressable onPress={load} style={zkp.refresh}>
            <Feather name="refresh-cw" size={13} color={colors.mutedForeground} />
          </Pressable>
        )}
      </View>

      {loading && <ActivityIndicator color={colors.primary} style={{ marginVertical: 16 }} />}

      {!loading && loaded && data && (
        <View style={{ gap: 12 }}>
          {/* Status banner */}
          <View style={[zkp.banner, { backgroundColor: `${statusColor}15`, borderColor: `${statusColor}33` }]}>
            <Text style={[zkp.bannerTxt, { color: statusColor }]}>{data.status_ar}</Text>
          </View>

          {/* Stats row */}
          <View style={zkp.statsRow}>
            <View style={zkp.statBlock}>
              <Text style={[zkp.statLbl, { color: colors.mutedForeground }]}>إجمالي الأرباح</Text>
              <Text style={[zkp.statVal, { color: colors.primary }]}>+${zk?.total_profit_usd.toFixed(2)}</Text>
            </View>
            <View style={[zkp.divider, { backgroundColor: colors.border }]} />
            <View style={zkp.statBlock}>
              <Text style={[zkp.statLbl, { color: colors.mutedForeground }]}>صافي الربح</Text>
              <Text style={[zkp.statVal, { color: (zk?.net_pnl_usd ?? 0) >= 0 ? colors.primary : "#FF6B6B" }]}>
                {(zk?.net_pnl_usd ?? 0) >= 0 ? "+" : ""}{zk?.net_pnl_usd.toFixed(2)}$
              </Text>
            </View>
            <View style={[zkp.divider, { backgroundColor: colors.border }]} />
            <View style={zkp.statBlock}>
              <Text style={[zkp.statLbl, { color: colors.mutedForeground }]}>الزكاة الواجبة</Text>
              <Text style={[zkp.statVal, { color: "#F59E0B", fontWeight: "800" as const }]}>
                ${zk?.zakat_due_usd.toFixed(2)}
              </Text>
            </View>
          </View>

          {/* Nisab progress */}
          <View style={{ gap: 6 }}>
            <View style={zkp.nisabRow}>
              <Text style={[zkp.cellLbl, { color: colors.mutedForeground }]}>
                النصاب (≈ $5,000) — {zk?.above_nisab ? "✅ بلغ النصاب" : "⬜ لم يبلغ النصاب"}
              </Text>
              <Text style={[zkp.cellLbl, { color: colors.mutedForeground }]}>
                ${zk?.net_pnl_usd.toFixed(0)} / $5,000
              </Text>
            </View>
            <View style={[zkp.progressTrack, { backgroundColor: colors.muted }]}>
              <View style={[zkp.progressFill, {
                width: `${Math.min(100, ((zk?.net_pnl_usd ?? 0) / 5000) * 100)}%` as any,
                backgroundColor: zk?.above_nisab ? "#F59E0B" : colors.primary,
              }]} />
            </View>
          </View>

          {/* Monthly breakdown */}
          {(data.monthly_profits?.length ?? 0) > 0 && (
            <View style={{ gap: 6 }}>
              <Text style={[zkp.cellLbl, { color: colors.mutedForeground }]}>الأرباح الشهرية</Text>
              {data.monthly_profits.slice(-6).map((m, i) => (
                <View key={i} style={[zkp.monthRow, { borderBottomColor: colors.border }]}>
                  <Text style={[zkp.monthLabel, { color: colors.foreground }]}>{m.month}</Text>
                  <Text style={[zkp.monthProfit, { color: colors.primary }]}>+${m.profit.toFixed(2)}</Text>
                  <Text style={[zkp.monthTrades, { color: colors.mutedForeground }]}>{m.trades} صفقة</Text>
                </View>
              ))}
            </View>
          )}

          {/* Notes */}
          <View style={[zkp.notesBox, { backgroundColor: `${colors.primary}08`, borderColor: `${colors.primary}22` }]}>
            {data.notes.map((n, i) => (
              <Text key={i} style={[zkp.noteTxt, { color: colors.mutedForeground }]}>• {n}</Text>
            ))}
          </View>
        </View>
      )}

      {!loading && !loaded && (
        <Text style={[zkp.hint, { color: colors.mutedForeground }]}>
          اضغط "احسب" لحساب الزكاة الواجبة على أرباح التداول
        </Text>
      )}
    </View>
  );
}
const zkp = StyleSheet.create({
  card:          { borderRadius: 16, borderWidth: 1, padding: 14, gap: 10 },
  header:        { flexDirection: "row" as const, alignItems: "flex-start" as const, justifyContent: "space-between" as const },
  loadBtn:       { paddingHorizontal: 14, paddingVertical: 6, borderRadius: 8, borderWidth: 1 },
  loadTxt:       { fontSize: 12, fontWeight: "700" as const },
  refresh:       { padding: 4 },
  banner:        { borderRadius: 10, borderWidth: 1, padding: 12 },
  bannerTxt:     { fontSize: 12, fontWeight: "600" as const, textAlign: "center" as const, lineHeight: 18 },
  statsRow:      { flexDirection: "row" as const, justifyContent: "space-around" as const },
  statBlock:     { flex: 1, alignItems: "center" as const, gap: 4 },
  divider:       { width: 1, marginVertical: 4 },
  statLbl:       { fontSize: 9, letterSpacing: 0.5, textAlign: "center" as const },
  statVal:       { fontSize: 16, fontWeight: "700" as const, fontFamily: "monospace" },
  nisabRow:      { flexDirection: "row" as const, justifyContent: "space-between" as const },
  progressTrack: { height: 6, borderRadius: 3, overflow: "hidden" as const },
  progressFill:  { height: 6, borderRadius: 3 },
  cellLbl:       { fontSize: 10 },
  monthRow:      { flexDirection: "row" as const, justifyContent: "space-between" as const, paddingVertical: 5, borderBottomWidth: 0.5 },
  monthLabel:    { fontSize: 11, fontFamily: "monospace", flex: 1 },
  monthProfit:   { fontSize: 11, fontWeight: "700" as const, fontFamily: "monospace", width: 80, textAlign: "right" as const },
  monthTrades:   { fontSize: 10, width: 60, textAlign: "right" as const },
  notesBox:      { borderRadius: 8, borderWidth: 1, padding: 10, gap: 4 },
  noteTxt:       { fontSize: 10, lineHeight: 16 },
  hint:          { fontSize: 11, textAlign: "center" as const, paddingVertical: 12, lineHeight: 18 },
});

// ── Portfolio Assets Panel ────────────────────────────────────────────────────

const AVAILABLE_SYMBOLS = [
  "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT",
  "ADA/USDT", "AVAX/USDT", "LINK/USDT", "DOT/USDT", "LTC/USDT",
  "NEAR/USDT", "TRX/USDT", "MATIC/USDT", "ATOM/USDT",
];

function PortfolioAssetsPanel({ colors }: { colors: any }) {
  const [assets, setAssets]   = useState<PortfolioAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving]   = useState(false);
  const [total, setTotal]     = useState(0);

  const load = async () => {
    try {
      const res = await fetch(`${getApiBase()}/portfolio/assets`);
      if (res.ok) {
        const d = await safeJson(res);
        setAssets(d?.assets ?? []);
        setTotal(d?.total_allocation ?? 0);
      }
    } catch { /* ignore */ }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const addSymbol = (sym: string) => {
    if (assets.find(a => a.symbol === sym)) return;
    const newA = [...assets, { symbol: sym, allocation_pct: 10, enabled: true }];
    setAssets(newA);
    recalcTotal(newA);
  };

  const removeSymbol = (sym: string) => {
    const newA = assets.filter(a => a.symbol !== sym);
    setAssets(newA);
    recalcTotal(newA);
  };

  const updateAlloc = (sym: string, val: number) => {
    const newA = assets.map(a => a.symbol === sym ? { ...a, allocation_pct: val } : a);
    setAssets(newA);
    recalcTotal(newA);
  };

  const toggleAsset = (sym: string) => {
    const newA = assets.map(a => a.symbol === sym ? { ...a, enabled: !a.enabled } : a);
    setAssets(newA);
    recalcTotal(newA);
  };

  const recalcTotal = (list: PortfolioAsset[]) => {
    setTotal(list.filter(a => a.enabled).reduce((s, a) => s + a.allocation_pct, 0));
  };

  const save = async () => {
    setSaving(true);
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    try {
      await fetch(`${getApiBase()}/portfolio/assets`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ assets }),
      });
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    } catch { /* ignore */ }
    finally { setSaving(false); }
  };

  const totalColor = total > 100 ? "#ef4444" : total >= 80 ? colors.primary : "#f97316";
  const availableToAdd = AVAILABLE_SYMBOLS.filter(s => !assets.find(a => a.symbol === s));

  return (
    <View style={[pap.card, { backgroundColor: colors.card, borderColor: colors.border }]}>
      <View style={pap.headerRow}>
        <SectionTitle icon="pie-chart" title="المحفظة المتعددة 📊" colors={colors} />
        <View style={[pap.totalBadge, { borderColor: `${totalColor}44`, backgroundColor: `${totalColor}15` }]}>
          <Text style={[pap.totalTxt, { color: totalColor }]}>{total.toFixed(0)}%</Text>
        </View>
      </View>

      <Text style={[pap.hint, { color: colors.mutedForeground }]}>
        حدد العملات التي يتداولها البوت ونسبة رأس المال لكل منها
      </Text>

      {loading ? (
        <ActivityIndicator color={colors.primary} />
      ) : (
        <>
          {/* Active assets */}
          {assets.length === 0 ? (
            <Text style={[pap.empty, { color: colors.mutedForeground }]}>لا توجد عملات — أضف من القائمة أدناه</Text>
          ) : (
            assets.map(a => (
              <View key={a.symbol} style={[pap.assetRow, { borderColor: colors.border }]}>
                <Pressable onPress={() => toggleAsset(a.symbol)} style={pap.assetLeft}>
                  <View style={[pap.dot, { backgroundColor: a.enabled ? colors.primary : colors.mutedForeground }]} />
                  <Text style={[pap.assetSym, { color: a.enabled ? colors.foreground : colors.mutedForeground }]}>
                    {a.symbol.replace("/USDT", "")}
                  </Text>
                </Pressable>
                <View style={pap.allocWrap}>
                  <TextInput
                    value={String(a.allocation_pct)}
                    onChangeText={v => { const n = parseFloat(v) || 0; updateAlloc(a.symbol, Math.min(100, n)); }}
                    keyboardType="numeric"
                    style={[pap.allocInput, { color: colors.foreground, borderColor: colors.border, backgroundColor: colors.background }]}
                  />
                  <Text style={[pap.pctSign, { color: colors.mutedForeground }]}>%</Text>
                </View>
                <Pressable onPress={() => removeSymbol(a.symbol)} style={pap.removeBtn}>
                  <Feather name="x" size={14} color="#FF6B6B" />
                </Pressable>
              </View>
            ))
          )}

          {/* Add symbol */}
          {availableToAdd.length > 0 && (
            <View style={{ gap: 6 }}>
              <Text style={[pap.hint, { color: colors.mutedForeground }]}>أضف عملة:</Text>
              <View style={pap.addChips}>
                {availableToAdd.map(s => (
                  <Pressable key={s} onPress={() => addSymbol(s)}
                    style={[pap.addChip, { borderColor: colors.border, backgroundColor: colors.background }]}>
                    <Feather name="plus" size={10} color={colors.primary} />
                    <Text style={[pap.addChipTxt, { color: colors.foreground }]}>{s.replace("/USDT", "")}</Text>
                  </Pressable>
                ))}
              </View>
            </View>
          )}

          {/* Save button */}
          {assets.length > 0 && (
            <TouchableOpacity onPress={save} disabled={saving || total > 100}
              style={[pap.saveBtn, { backgroundColor: total > 100 ? "#4444" : colors.primary }]}>
              {saving ? <ActivityIndicator color="#fff" size="small" /> : (
                <>
                  <Feather name="save" size={13} color="#fff" />
                  <Text style={pap.saveTxt}>حفظ وتطبيق</Text>
                </>
              )}
            </TouchableOpacity>
          )}

          {total > 100 && (
            <Text style={{ color: "#ef4444", fontSize: 11, textAlign: "center" as const }}>
              مجموع النسب {total.toFixed(0)}% يتجاوز 100%
            </Text>
          )}
        </>
      )}
    </View>
  );
}
const pap = StyleSheet.create({
  card:       { borderRadius: 16, borderWidth: 1, padding: 14, gap: 10 },
  headerRow:  { flexDirection: "row" as const, alignItems: "flex-start" as const, justifyContent: "space-between" as const },
  totalBadge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8, borderWidth: 1 },
  totalTxt:   { fontSize: 13, fontWeight: "700" as const, fontFamily: "monospace" },
  hint:       { fontSize: 10, lineHeight: 15 },
  empty:      { textAlign: "center" as const, paddingVertical: 12, fontSize: 11 },
  assetRow:   { flexDirection: "row" as const, alignItems: "center" as const, gap: 8, paddingVertical: 8, borderBottomWidth: 1 },
  assetLeft:  { flex: 1, flexDirection: "row" as const, alignItems: "center" as const, gap: 8 },
  dot:        { width: 8, height: 8, borderRadius: 4 },
  assetSym:   { fontSize: 13, fontWeight: "700" as const },
  allocWrap:  { flexDirection: "row" as const, alignItems: "center" as const, gap: 2 },
  allocInput: { width: 44, textAlign: "center" as const, borderWidth: 1, borderRadius: 6, paddingVertical: 4, fontSize: 13, fontFamily: "monospace" },
  pctSign:    { fontSize: 12 },
  removeBtn:  { padding: 4 },
  addChips:   { flexDirection: "row" as const, gap: 6, flexWrap: "wrap" as const },
  addChip:    { flexDirection: "row" as const, alignItems: "center" as const, gap: 4, paddingHorizontal: 9, paddingVertical: 5, borderRadius: 8, borderWidth: 1 },
  addChipTxt: { fontSize: 11, fontWeight: "600" as const },
  saveBtn:    { borderRadius: 10, padding: 11, alignItems: "center" as const, flexDirection: "row" as const, justifyContent: "center" as const, gap: 8 },
  saveTxt:    { color: "#fff", fontSize: 13, fontWeight: "700" as const },
});

// ── Empty State ───────────────────────────────────────────────────────────────

function EmptyState({ colors }: { colors: any }) {
  return (
    <View style={em.wrap}>
      <View style={[em.circle, { backgroundColor: `${colors.primary}14` }]}>
        <Feather name="pie-chart" size={32} color={colors.primary} />
      </View>
      <Text style={[em.title, { color: colors.foreground }]}>لا توجد صفقات مغلقة بعد</Text>
      <Text style={[em.sub, { color: colors.mutedForeground }]}>
        بمجرد إغلاق أول صفقة، ستظهر هنا رسوم بيانية التحليلات الكاملة
      </Text>
    </View>
  );
}
const em = StyleSheet.create({
  wrap:   { alignItems: "center" as const, paddingVertical: 60, paddingHorizontal: 32, gap: 12 },
  circle: { width: 72, height: 72, borderRadius: 36, alignItems: "center" as const, justifyContent: "center" as const },
  title:  { fontSize: 16, fontWeight: "700" as const, textAlign: "center" as const },
  sub:    { fontSize: 13, textAlign: "center" as const, lineHeight: 20, opacity: 0.7 },
});

// ── Section Header ────────────────────────────────────────────────────────────

function SectionTitle({ icon, title, colors }: { icon: string; title: string; colors: any }) {
  return (
    <View style={{ flexDirection: "row", alignItems: "center", gap: 8, marginBottom: 10 }}>
      <View style={[sth.icon, { backgroundColor: `${colors.primary}18` }]}>
        <Feather name={icon as any} size={12} color={colors.primary} />
      </View>
      <Text style={[sth.title, { color: colors.foreground }]}>{title}</Text>
    </View>
  );
}
const sth = StyleSheet.create({
  icon:  { width: 24, height: 24, borderRadius: 7, alignItems: "center" as const, justifyContent: "center" as const },
  title: { fontSize: 13, fontWeight: "800" as const, letterSpacing: -0.2 },
});

// ── Main Screen ───────────────────────────────────────────────────────────────

export default function AnalyticsScreen() {
  const colors = useColors();
  const insets = useSafeAreaInsets();

  const [data, setData]       = useState<ChartData | null>(null);
  const [range, setRange]     = useState<Range>("0");
  const [loading, setLoading] = useState(true);
  const [chartW, setChartW]   = useState(320);
  const [refreshing, setRefreshing] = useState(false);

  const topPad = Platform.OS === "web" ? 67 : insets.top;
  const botPad = Platform.OS === "web" ? 34 : insets.bottom;

  const load = useCallback(async (r = range) => {
    try {
      const res = await fetch(`${getApiBase()}/portfolio/chart?days=${r}`);
      if (res.ok) setData(await safeJson(res));
    } catch { /* ignore */ }
    finally { setLoading(false); setRefreshing(false); }
  }, [range]);

  useEffect(() => { setLoading(true); load(range); }, [range]);

  const onRefresh = () => { setRefreshing(true); load(range); };

  const s = data?.summary;
  const hasData = (s?.total_trades ?? 0) > 0;
  const pnlColor = (s?.total_pnl ?? 0) >= 0 ? colors.primary : "#FF6B6B";
  const maxSymPnl = Math.max(0.0001, ...(data?.by_symbol.map(x => Math.abs(x.pnl)) ?? [0]));

  return (
    <ScrollView
      style={[styles.root, { backgroundColor: colors.background }]}
      contentContainerStyle={{ paddingBottom: botPad + 90 }}
      showsVerticalScrollIndicator={false}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
    >
      {/* ── Header ── */}
      <View style={[styles.header, { paddingTop: topPad + 10, borderBottomColor: colors.border }]}>
        <View>
          <Text style={[styles.title, { color: colors.foreground }]}>تحليلات</Text>
          <Text style={[styles.subtitle, { color: colors.mutedForeground }]}>
            {hasData ? `${s?.total_trades} صفقة مغلقة` : "في انتظار الصفقات"}
          </Text>
        </View>

        {/* Range selector */}
        <View style={[styles.rangeRow, { backgroundColor: colors.card, borderColor: colors.border }]}>
          {RANGES.map(r => (
            <Pressable
              key={r.key}
              onPress={() => { Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light); setRange(r.key); }}
              style={[styles.rangeBtn, range === r.key && { backgroundColor: colors.primary, borderRadius: 8 }]}
            >
              <Text style={[styles.rangeTxt, { color: range === r.key ? colors.primaryForeground : colors.mutedForeground }]}>
                {r.label}
              </Text>
            </Pressable>
          ))}
        </View>
      </View>

      {loading ? (
        <View style={{ paddingTop: 80, alignItems: "center" }}>
          <ActivityIndicator size="large" color={colors.primary} />
          <Text style={{ color: colors.mutedForeground, marginTop: 12, fontSize: 12 }}>جارٍ التحميل...</Text>
        </View>
      ) : !hasData ? (
        <EmptyState colors={colors} />
      ) : (
        <View style={{ paddingHorizontal: 16, gap: 16, paddingTop: 16 }}>

          {/* ── Stats Row 1 ── */}
          <View style={styles.row}>
            <StatCard
              icon="trending-up" label="إجمالي PnL"
              value={fmt(s?.total_pnl ?? 0)}
              sub={`ROI: ${(s?.roi_percent ?? 0) >= 0 ? "+" : ""}${s?.roi_percent?.toFixed(2)}%`}
              color={pnlColor}
            />
            <StatCard
              icon="percent" label="نسبة الفوز"
              value={`${s?.win_rate?.toFixed(1)}%`}
              sub={`${s?.wins}ر / ${s?.losses}خ`}
              color={colors.primary}
            />
            <StatCard
              icon="zap" label="عامل الربح"
              value={(s?.profit_factor ?? 0) >= 9.9 ? "∞" : `${s?.profit_factor?.toFixed(2)}×`}
              sub="Profit Factor"
              color="#F59E0B"
            />
          </View>

          {/* ── Stats Row 2 ── */}
          <View style={styles.row}>
            <StatCard
              icon="arrow-up-right" label="متوسط الربح"
              value={fmt(s?.avg_win ?? 0)}
              color={colors.primary}
            />
            <StatCard
              icon="arrow-down-right" label="متوسط الخسارة"
              value={fmt(-(s?.avg_loss ?? 0))}
              color="#FF6B6B"
            />
            <StatCard
              icon="layers" label="إجمالي الصفقات"
              value={`${s?.total_trades}`}
              sub={`${data?.by_symbol.length ?? 0} عملة`}
              color={colors.mutedForeground}
            />
          </View>

          {/* ── Cumulative PnL Chart ── */}
          <View
            style={[styles.card, { borderColor: colors.border, backgroundColor: colors.card }]}
            onLayout={e => setChartW(e.nativeEvent.layout.width - 24)}
          >
            <SectionTitle icon="trending-up" title="منحنى الأرباح التراكمي" colors={colors} />
            {(data?.cumulative.length ?? 0) > 1 ? (
              <LineChart data={data!.cumulative} width={chartW} primaryColor={colors.primary} />
            ) : (
              <View style={{ height: CHART_H, alignItems: "center", justifyContent: "center" }}>
                <Text style={{ color: colors.mutedForeground, fontSize: 12 }}>تحتاج صفقتين على الأقل</Text>
              </View>
            )}
          </View>

          {/* ── Daily PnL Bars ── */}
          {(data?.daily.length ?? 0) > 0 && (
            <View style={[styles.card, { borderColor: colors.border, backgroundColor: colors.card }]}>
              <SectionTitle icon="bar-chart-2" title="PnL اليومي" colors={colors} />
              <BarChart data={data!.daily} width={chartW} primaryColor={colors.primary} />
              <View style={[styles.barLegend]}>
                <View style={styles.legendItem}>
                  <View style={[styles.legendDot, { backgroundColor: colors.primary }]} />
                  <Text style={[styles.legendTxt, { color: colors.mutedForeground }]}>ربح</Text>
                </View>
                <View style={styles.legendItem}>
                  <View style={[styles.legendDot, { backgroundColor: "#FF6B6B" }]} />
                  <Text style={[styles.legendTxt, { color: colors.mutedForeground }]}>خسارة</Text>
                </View>
              </View>
            </View>
          )}

          {/* ── Streaks ── */}
          {data && (
            <View>
              <SectionTitle icon="award" title="سلاسل الأداء" colors={colors} />
              <View style={styles.row}>
                <StreakBadge
                  type="win"
                  count={data.streak.current_type === "win" ? data.streak.current_count : 0}
                  label="السلسلة الحالية"
                  color={data.streak.current_type === "win" ? colors.primary : "#FF6B6B"}
                />
                <View style={{ width: 8 }} />
                <StreakBadge
                  type="best"
                  count={data.streak.best_win}
                  label="أفضل سلسلة فوز"
                  color={colors.primary}
                />
                <View style={{ width: 8 }} />
                <StreakBadge
                  type="worst"
                  count={data.streak.best_loss}
                  label="أطول سلسلة خسارة"
                  color="#FF6B6B"
                />
              </View>
            </View>
          )}

          {/* ── Best Trades ── */}
          {(data?.top_trades.length ?? 0) > 0 && (
            <View style={[styles.card, { borderColor: colors.border, backgroundColor: colors.card }]}>
              <SectionTitle icon="star" title="أفضل الصفقات 🏆" colors={colors} />
              {data!.top_trades.slice(0, 5).map((t, i) => (
                <TradeRow key={i} trade={t} isTop />
              ))}
            </View>
          )}

          {/* ── Worst Trades ── */}
          {(data?.bottom_trades.length ?? 0) > 0 && (
            <View style={[styles.card, { borderColor: colors.border, backgroundColor: colors.card }]}>
              <SectionTitle icon="alert-circle" title="أسوأ الصفقات 📉" colors={colors} />
              {data!.bottom_trades.slice(0, 5).map((t, i) => (
                <TradeRow key={i} trade={t} isTop={false} />
              ))}
            </View>
          )}

          {/* ── By Symbol ── */}
          {(data?.by_symbol.length ?? 0) > 0 && (
            <View style={[styles.card, { borderColor: colors.border, backgroundColor: colors.card }]}>
              <SectionTitle icon="pie-chart" title="الأداء حسب العملة" colors={colors} />
              <View style={[styles.symHeader, { borderBottomColor: colors.border }]}>
                <Text style={[styles.symHdrTxt, { color: colors.mutedForeground, width: 36 }]}>رمز</Text>
                <Text style={[styles.symHdrTxt, { color: colors.mutedForeground, flex: 1 }]}>الأداء</Text>
                <Text style={[styles.symHdrTxt, { color: colors.mutedForeground, width: 30 }]}>فوز%</Text>
                <Text style={[styles.symHdrTxt, { color: colors.mutedForeground, width: 58, textAlign: "right" }]}>PnL</Text>
              </View>
              {data!.by_symbol.slice(0, 8).map((sym, i) => (
                <SymbolBar key={i} sym={sym} max={maxSymPnl} primaryColor={colors.primary} />
              ))}
            </View>
          )}

        </View>
      )}

      {/* ══════════════ ALWAYS VISIBLE PANELS ══════════════ */}
      <View style={{ paddingHorizontal: 16, gap: 16, paddingTop: hasData ? 0 : 16, paddingBottom: 8 }}>

        {/* ── Multi-Asset Portfolio ── */}
        <PortfolioAssetsPanel colors={colors} />

        {/* ── Backtesting ── */}
        <BacktestPanel colors={colors} />

        {/* ── Zakat Calculator ── */}
        <ZakatPanel colors={colors} />

      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  root:       { flex: 1 },
  header:     {
    paddingHorizontal: 16, paddingBottom: 14, borderBottomWidth: 1,
    flexDirection: "row" as const, alignItems: "flex-end" as const, justifyContent: "space-between" as const,
  },
  title:      { fontSize: 26, fontWeight: "800" as const, letterSpacing: -0.8 },
  subtitle:   { fontSize: 11, marginTop: 2 },
  rangeRow:   {
    flexDirection: "row" as const, borderRadius: 10, borderWidth: 1,
    padding: 3, gap: 2,
  },
  rangeBtn:   { paddingHorizontal: 10, paddingVertical: 6 },
  rangeTxt:   { fontSize: 11, fontWeight: "700" as const },
  row:        { flexDirection: "row" as const, gap: 8 },
  card:       { borderRadius: 16, borderWidth: 1, padding: 14 },
  barLegend:  { flexDirection: "row" as const, gap: 14, justifyContent: "flex-end" as const, marginTop: 4 },
  legendItem: { flexDirection: "row" as const, alignItems: "center" as const, gap: 5 },
  legendDot:  { width: 8, height: 8, borderRadius: 4 },
  legendTxt:  { fontSize: 10 },
  symHeader:  { flexDirection: "row" as const, alignItems: "center" as const, paddingBottom: 6, borderBottomWidth: 1, marginBottom: 4 },
  symHdrTxt:  { fontSize: 9, fontWeight: "700" as const, letterSpacing: 0.3 },
});
