import { Feather } from "@expo/vector-icons";
import React, { useState } from "react";
import {
  FlatList,
  Linking,
  Platform,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { getApiBase } from "@/constants/api";
import { useBotContext } from "@/context/BotContext";
import { useColors } from "@/hooks/useColors";
import type { Trade } from "@/types";

type Filter = "all" | "open" | "win" | "loss";

const FILTERS: { key: Filter; label: string; icon: string }[] = [
  { key: "all",  label: "ALL",  icon: "list" },
  { key: "open", label: "OPEN", icon: "activity" },
  { key: "win",  label: "WIN",  icon: "trending-up" },
  { key: "loss", label: "LOSS", icon: "trending-down" },
];

function applyFilter(trades: Trade[], filter: Filter): Trade[] {
  switch (filter) {
    case "open": return trades.filter((t) => t.status === "open");
    case "win":  return trades.filter((t) => t.status === "closed" && (t.pnl ?? 0) > 0);
    case "loss": return trades.filter((t) => t.status === "closed" && (t.pnl ?? 0) <= 0);
    default:     return trades;
  }
}

function calcPnlPct(trade: Trade): number | null {
  if (trade.pnl_percent != null) return trade.pnl_percent;
  const ep = trade.entry_price;
  const xp = trade.exit_price;
  if (!ep || !xp) return null;
  const raw = (xp - ep) / ep * 100;
  return trade.side === "buy" ? raw : -raw;
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1)  return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24)  return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

function fmtDateTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" })
    + " " + d.toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit" });
}

function fmtDuration(open: string, close: string | null): string {
  if (!close) return "open";
  const mins = Math.floor((new Date(close).getTime() - new Date(open).getTime()) / 60000);
  if (mins < 60)  return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24)   return `${hrs}h ${mins % 60}m`;
  return `${Math.floor(hrs / 24)}d ${hrs % 24}h`;
}

function fmtPrice(p: number | null | undefined): string {
  if (p == null) return "—";
  if (p >= 1000) return `$${p.toFixed(1)}`;
  if (p >= 1)    return `$${p.toFixed(3)}`;
  return `$${p.toFixed(5)}`;
}

function SlTpBar({
  side, entry, sl, tp, colors,
}: { side: string; entry: number; sl: number | null | undefined; tp: number | null | undefined; colors: any }) {
  if (!sl || !tp || !entry) return null;
  const range = Math.abs(tp - sl);
  if (range === 0) return null;
  const entryPct = ((entry - sl) / range) * 100;

  return (
    <View style={bar.wrap}>
      <Text style={[bar.label, { color: colors.destructive }]}>SL</Text>
      <View style={[bar.track, { backgroundColor: colors.muted }]}>
        <View style={[bar.danger, { width: `${Math.min(entryPct, 100)}%`, backgroundColor: `${colors.destructive}55` }]} />
        <View style={[bar.success, { width: `${Math.min(100 - entryPct, 100)}%`, backgroundColor: `${colors.primary}55` }]} />
        <View style={[bar.pin, { left: `${Math.min(Math.max(entryPct, 2), 98)}%` as any }]} />
      </View>
      <Text style={[bar.label, { color: colors.primary }]}>TP</Text>
    </View>
  );
}

const bar = StyleSheet.create({
  wrap: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 8 },
  track: { flex: 1, height: 6, borderRadius: 3, flexDirection: "row", overflow: "hidden" },
  danger: { height: "100%" },
  success: { height: "100%" },
  pin: { position: "absolute", top: -3, width: 2, height: 12, backgroundColor: "#fff", borderRadius: 1 },
  label: { fontSize: 8, fontWeight: "800" as const, letterSpacing: 0.5, width: 14 },
});

function TradeCard({ trade, index }: { trade: Trade; index: number }) {
  const colors = useColors();
  const [expanded, setExpanded] = useState(false);

  const isBuy    = trade.side === "buy";
  const isOpen   = trade.status === "open";
  const isWin    = (trade.pnl ?? 0) > 0;
  const pnl      = trade.pnl ?? 0;
  const pnlPct   = calcPnlPct(trade);

  const pnlColor   = isOpen ? (colors.cyan ?? "#00D4FF") : isWin ? colors.primary : colors.destructive;
  const sideColor  = isBuy ? colors.primary : colors.destructive;
  const accentColor = isOpen ? (colors.cyan ?? "#00D4FF") : isWin ? colors.primary : colors.destructive;

  return (
    <Pressable
      onPress={() => setExpanded((v) => !v)}
      style={[
        card.container,
        {
          backgroundColor: colors.card,
          borderLeftColor: accentColor,
          borderColor: expanded ? `${accentColor}44` : colors.border,
        },
      ]}
    >
      {/* ── Main row ── */}
      <View style={card.mainRow}>
        {/* Side + symbol */}
        <View style={card.colSymbol}>
          <View style={[card.sideBadge, { backgroundColor: `${sideColor}20`, borderColor: `${sideColor}55` }]}>
            <Text style={[card.sideText, { color: sideColor }]}>{isBuy ? "BUY" : "SELL"}</Text>
          </View>
          <View>
            <Text style={[card.symbol, { color: colors.foreground }]}>
              {trade.symbol.replace("/USDT", "")}
              <Text style={[card.usdt, { color: colors.mutedForeground }]}>/USDT</Text>
            </Text>
            <Text style={[card.timeAgo, { color: colors.mutedForeground }]}>{timeAgo(trade.created_at)}</Text>
          </View>
        </View>

        {/* Entry price */}
        <View style={card.colPrice}>
          <Text style={[card.priceVal, { color: colors.foreground }]}>{fmtPrice(trade.entry_price)}</Text>
          <Text style={[card.priceLabel, { color: colors.mutedForeground }]}>entry</Text>
        </View>

        {/* AI + ML confidence */}
        <View style={card.colConf}>
          <Text style={[
            card.confVal,
            { color: trade.ai_confidence >= 80 ? colors.primary : trade.ai_confidence >= 70 ? (colors.warning ?? "#FF9F43") : colors.mutedForeground },
          ]}>
            {trade.ai_confidence}%
          </Text>
          {trade.ml_win_prob != null ? (
            <Text style={[card.mlProb, {
              color: trade.ml_win_prob >= 0.65 ? colors.primary
                : trade.ml_win_prob >= 0.5 ? (colors.warning ?? "#FF9F43")
                : colors.destructive,
            }]}>
              ML {Math.round(trade.ml_win_prob * 100)}%
            </Text>
          ) : (
            <Text style={[card.confLabel, { color: colors.mutedForeground }]}>AI</Text>
          )}
        </View>

        {/* PnL */}
        <View style={card.colPnl}>
          {isOpen ? (
            <View style={[card.openBadge, { backgroundColor: `${colors.cyan ?? "#00D4FF"}18`, borderColor: `${colors.cyan ?? "#00D4FF"}44` }]}>
              <View style={[card.liveDot, { backgroundColor: colors.cyan ?? "#00D4FF" }]} />
              <Text style={[card.openText, { color: colors.cyan ?? "#00D4FF" }]}>LIVE</Text>
            </View>
          ) : (
            <>
              <Text style={[card.pnlAmt, { color: pnlColor }]}>
                {pnl >= 0 ? "+" : ""}${Math.abs(pnl).toFixed(3)}
              </Text>
              {pnlPct != null && (
                <View style={[card.pnlPctBadge, { backgroundColor: `${pnlColor}18` }]}>
                  <Text style={[card.pnlPct, { color: pnlColor }]}>
                    {pnlPct >= 0 ? "+" : ""}{pnlPct.toFixed(2)}%
                  </Text>
                </View>
              )}
            </>
          )}
        </View>

        {/* Expand chevron */}
        <Feather
          name={expanded ? "chevron-up" : "chevron-down"}
          size={12}
          color={colors.mutedForeground}
          style={{ marginLeft: 4 }}
        />
      </View>

      {/* ── Expanded detail panel ── */}
      {expanded && (
        <View style={[card.detail, { borderTopColor: colors.border }]}>

          {/* SL/TP bar */}
          <SlTpBar
            side={trade.side}
            entry={trade.entry_price}
            sl={trade.stop_loss_price}
            tp={trade.take_profit_price}
            colors={colors}
          />

          {/* Price grid */}
          <View style={card.detailGrid}>
            {[
              { label: "ENTRY",    val: fmtPrice(trade.entry_price),      color: colors.foreground },
              { label: "EXIT",     val: fmtPrice(trade.exit_price),        color: isOpen ? colors.mutedForeground : (isWin ? colors.primary : colors.destructive) },
              { label: "STOP LOSS",val: fmtPrice(trade.stop_loss_price),   color: colors.destructive },
              { label: "TAKE PROF",val: fmtPrice(trade.take_profit_price), color: colors.primary },
              { label: "QTY",      val: (trade.quantity ?? 0).toFixed(5),  color: colors.foreground },
              { label: "DURATION", val: fmtDuration(trade.created_at, trade.closed_at), color: colors.mutedForeground },
            ].map((item) => (
              <View key={item.label} style={card.detailItem}>
                <Text style={[card.detailLabel, { color: colors.mutedForeground }]}>{item.label}</Text>
                <Text style={[card.detailVal, { color: item.color }]}>{item.val}</Text>
              </View>
            ))}
          </View>

          {/* Pattern + market condition */}
          {(trade.pattern || trade.market_condition) && (
            <View style={card.tagsRow}>
              {trade.pattern ? (
                <View style={[card.tag, { backgroundColor: `${colors.primary}18`, borderColor: `${colors.primary}33` }]}>
                  <Feather name="zap" size={9} color={colors.primary} />
                  <Text style={[card.tagText, { color: colors.primary }]}>{trade.pattern}</Text>
                </View>
              ) : null}
              {trade.market_condition ? (
                <View style={[card.tag, { backgroundColor: `${colors.mutedForeground}15`, borderColor: `${colors.mutedForeground}30` }]}>
                  <Feather name="bar-chart-2" size={9} color={colors.mutedForeground} />
                  <Text style={[card.tagText, { color: colors.mutedForeground }]}>{trade.market_condition}</Text>
                </View>
              ) : null}
            </View>
          )}

          {/* AI reasoning */}
          {trade.ai_reasoning ? (
            <View style={[card.reasoningWrap, { backgroundColor: `${colors.primary}08`, borderColor: `${colors.primary}20` }]}>
              <Text style={[card.reasoningLabel, { color: colors.mutedForeground }]}>AI REASONING</Text>
              <Text style={[card.reasoningText, { color: colors.mutedForeground }]}>{trade.ai_reasoning}</Text>
            </View>
          ) : null}

          {/* Opened / closed timestamps */}
          <View style={card.datesRow}>
            <Text style={[card.dateText, { color: colors.mutedForeground }]}>
              Opened: {fmtDateTime(trade.created_at)}
            </Text>
            {trade.closed_at && (
              <Text style={[card.dateText, { color: colors.mutedForeground }]}>
                Closed: {fmtDateTime(trade.closed_at)}
              </Text>
            )}
          </View>
        </View>
      )}
    </Pressable>
  );
}

export default function TradesScreen() {
  const colors = useColors();
  const insets = useSafeAreaInsets();
  const { trades, portfolio, isTradesLoading, refreshTrades, refreshPortfolio } = useBotContext();
  const [filter, setFilter] = useState<Filter>("all");

  const filtered  = applyFilter(trades, filter);
  const totalPnl  = portfolio?.total_pnl ?? 0;
  const roiPct    = portfolio?.roi_percent ?? 0;
  const topPad    = Platform.OS === "web" ? 67 : insets.top;
  const bottomPad = Platform.OS === "web" ? 34 : insets.bottom;

  const handleRefresh = async () => {
    await Promise.all([refreshTrades(), refreshPortfolio()]);
  };

  const handleExport = () => {
    Linking.openURL(`${getApiBase()}/trades/export/csv`);
  };

  return (
    <View style={[styles.root, { backgroundColor: colors.background }]}>

      {/* ── Header ── */}
      <View style={[styles.header, { paddingTop: topPad + 10, borderBottomColor: colors.border }]}>
        <View>
          <Text style={[styles.headerLabel, { color: colors.mutedForeground }]}>TRADE HISTORY</Text>
          <Text style={[styles.headerTitle, { color: colors.foreground }]}>Positions</Text>
        </View>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 12 }}>
          <Pressable
            onPress={handleExport}
            style={[styles.exportBtn, { borderColor: colors.border, backgroundColor: colors.card }]}
          >
            <Feather name="download" size={13} color={colors.primary} />
            <Text style={[styles.exportLabel, { color: colors.primary }]}>CSV</Text>
          </Pressable>
          <View style={styles.headerRight}>
            <Text style={[styles.pnlLarge, { color: totalPnl >= 0 ? colors.primary : colors.destructive }]}>
              {totalPnl >= 0 ? "+" : ""}{totalPnl.toFixed(4)}
            </Text>
            <Text style={[styles.roiSmall, { color: roiPct >= 0 ? colors.primary : colors.destructive }]}>
              {roiPct >= 0 ? "▲" : "▼"} {Math.abs(roiPct).toFixed(2)}% ROI
            </Text>
          </View>
        </View>
      </View>

      {/* ── Stats bar ── */}
      {portfolio && (
        <View style={[styles.statsBar, { backgroundColor: colors.card, borderBottomColor: colors.border }]}>
          {[
            {
              label: "WIN RATE",
              value: `${portfolio.win_rate.toFixed(1)}%`,
              color: portfolio.win_rate >= portfolio.target_win_rate ? colors.primary : (colors.warning ?? "#FF9F43"),
            },
            {
              label: "P.FACTOR",
              value: `${portfolio.profit_factor.toFixed(2)}x`,
              color: portfolio.profit_factor >= 1.5 ? colors.primary : portfolio.profit_factor >= 1 ? (colors.warning ?? "#FF9F43") : colors.destructive,
            },
            {
              label: "AVG WIN",
              value: `$${portfolio.avg_win.toFixed(3)}`,
              color: colors.primary,
            },
            {
              label: "AVG LOSS",
              value: `$${portfolio.avg_loss.toFixed(3)}`,
              color: colors.destructive,
            },
          ].map((s) => (
            <View key={s.label} style={styles.statItem}>
              <Text style={[styles.statLabel, { color: colors.mutedForeground }]}>{s.label}</Text>
              <Text style={[styles.statValue, { color: s.color }]}>{s.value}</Text>
            </View>
          ))}
        </View>
      )}

      {/* ── Filter tabs ── */}
      <View style={[styles.filterRow, { borderBottomColor: colors.border }]}>
        {FILTERS.map((f) => {
          const count  = applyFilter(trades, f.key).length;
          const active = filter === f.key;
          return (
            <Pressable
              key={f.key}
              onPress={() => setFilter(f.key)}
              style={[styles.filterBtn, { borderBottomColor: active ? colors.primary : "transparent", borderBottomWidth: 2 }]}
            >
              <Text style={[styles.filterLabel, { color: active ? colors.primary : colors.mutedForeground }]}>
                {f.label}
              </Text>
              <View style={[styles.filterBadge, { backgroundColor: active ? `${colors.primary}22` : colors.muted }]}>
                <Text style={[styles.filterCount, { color: active ? colors.primary : colors.mutedForeground }]}>
                  {count}
                </Text>
              </View>
            </Pressable>
          );
        })}
      </View>

      {/* ── Trade list ── */}
      <FlatList
        data={filtered}
        keyExtractor={(item) => item.id}
        renderItem={({ item, index }) => <TradeCard trade={item} index={index} />}
        refreshControl={
          <RefreshControl
            refreshing={isTradesLoading}
            onRefresh={handleRefresh}
            tintColor={colors.primary}
          />
        }
        ListHeaderComponent={
          filtered.length > 0 ? (
            <View style={[styles.listHeader, { borderBottomColor: colors.border }]}>
              <Text style={[styles.listHeaderTip, { color: colors.mutedForeground }]}>
                Tap any position to view full details
              </Text>
              <Text style={[styles.listHeaderCount, { color: colors.mutedForeground }]}>
                {filtered.length} position{filtered.length !== 1 ? "s" : ""}
              </Text>
            </View>
          ) : null
        }
        ListEmptyComponent={
          <View style={[styles.empty, { backgroundColor: colors.card, borderColor: colors.border }]}>
            <Feather name="inbox" size={28} color={`${colors.mutedForeground}55`} />
            <Text style={[styles.emptyLine1, { color: colors.mutedForeground }]}>
              {filter === "all" ? "No positions yet" : `No ${filter} positions`}
            </Text>
            <Text style={[styles.emptyLine2, { color: `${colors.mutedForeground}88` }]}>
              {filter === "all"
                ? "Start the autopilot — positions appear here in real-time"
                : `Filter by ALL to see your complete history`}
            </Text>
          </View>
        }
        contentContainerStyle={[
          filtered.length === 0 && styles.listEmpty,
          { paddingBottom: bottomPad + 80, paddingTop: 4 },
        ]}
        showsVerticalScrollIndicator={false}
      />
    </View>
  );
}

const card = StyleSheet.create({
  container: {
    marginHorizontal: 12,
    marginVertical: 4,
    borderRadius: 12,
    borderWidth: 1,
    borderLeftWidth: 3,
    overflow: "hidden",
  },
  mainRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 12,
    paddingHorizontal: 12,
  },
  colSymbol: { flex: 2.5, flexDirection: "row", alignItems: "center", gap: 8 },
  sideBadge: {
    paddingHorizontal: 5,
    paddingVertical: 3,
    borderRadius: 5,
    borderWidth: 1,
  },
  sideText: { fontSize: 9, fontWeight: "800" as const, letterSpacing: 0.8 },
  symbol: { fontSize: 13, fontWeight: "700" as const, fontFamily: "monospace" },
  usdt: { fontSize: 9 },
  timeAgo: { fontSize: 9, marginTop: 1 },
  colPrice: { flex: 2, alignItems: "flex-start" },
  priceVal: { fontSize: 11, fontFamily: "monospace", fontWeight: "600" as const },
  priceLabel: { fontSize: 8, letterSpacing: 0.5 },
  colConf: { flex: 1.2, alignItems: "center" },
  confVal: { fontSize: 11, fontFamily: "monospace", fontWeight: "700" as const },
  confLabel: { fontSize: 8, letterSpacing: 0.5 },
  mlProb: { fontSize: 8, fontFamily: "monospace", fontWeight: "700" as const, letterSpacing: 0.3 },
  colPnl: { flex: 2, alignItems: "flex-end" },
  openBadge: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 7, paddingVertical: 4, borderRadius: 6, borderWidth: 1 },
  liveDot: { width: 5, height: 5, borderRadius: 2.5 },
  openText: { fontSize: 9, fontWeight: "800" as const, letterSpacing: 1 },
  pnlAmt: { fontSize: 12, fontFamily: "monospace", fontWeight: "700" as const },
  pnlPctBadge: { paddingHorizontal: 5, paddingVertical: 2, borderRadius: 4, marginTop: 2 },
  pnlPct: { fontSize: 9, fontFamily: "monospace", fontWeight: "700" as const },

  detail: { borderTopWidth: 1, paddingHorizontal: 12, paddingBottom: 14, paddingTop: 10, gap: 8 },
  detailGrid: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 4 },
  detailItem: { width: "30%", minWidth: 90 },
  detailLabel: { fontSize: 8, letterSpacing: 1, fontWeight: "700" as const, marginBottom: 3 },
  detailVal: { fontSize: 12, fontFamily: "monospace", fontWeight: "600" as const },

  tagsRow: { flexDirection: "row", gap: 6, flexWrap: "wrap" },
  tag: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6, borderWidth: 1 },
  tagText: { fontSize: 10, fontWeight: "600" as const },

  reasoningWrap: { borderRadius: 8, padding: 10, borderWidth: 1 },
  reasoningLabel: { fontSize: 8, letterSpacing: 1, fontWeight: "700" as const, marginBottom: 5 },
  reasoningText: { fontSize: 11, lineHeight: 16 },

  datesRow: { gap: 2 },
  dateText: { fontSize: 9, fontFamily: "monospace" },
});

const styles = StyleSheet.create({
  root: { flex: 1 },
  header: {
    flexDirection: "row",
    alignItems: "flex-end",
    justifyContent: "space-between",
    paddingHorizontal: 18,
    paddingBottom: 14,
    borderBottomWidth: 1,
  },
  headerLabel: { fontSize: 9, letterSpacing: 2, fontWeight: "700" as const, marginBottom: 4 },
  headerTitle: { fontSize: 24, fontWeight: "700" as const, letterSpacing: -0.5 },
  headerRight: { alignItems: "flex-end" },
  exportBtn: { flexDirection: "row", alignItems: "center", gap: 5, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, borderWidth: 1 },
  exportLabel: { fontSize: 10, fontWeight: "700" as const, letterSpacing: 1 },
  pnlLarge: { fontSize: 18, fontWeight: "700" as const, fontFamily: "monospace" },
  roiSmall: { fontSize: 11, fontFamily: "monospace", fontWeight: "600" as const, marginTop: 2 },
  statsBar: { flexDirection: "row", paddingVertical: 10, borderBottomWidth: 1 },
  statItem: { flex: 1, alignItems: "center" },
  statLabel: { fontSize: 7, letterSpacing: 1, fontWeight: "700" as const, marginBottom: 3 },
  statValue: { fontSize: 12, fontWeight: "700" as const, fontFamily: "monospace" },
  filterRow: { flexDirection: "row", paddingHorizontal: 4, borderBottomWidth: 1 },
  filterBtn: { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, paddingVertical: 10 },
  filterLabel: { fontSize: 10, fontWeight: "700" as const, letterSpacing: 1 },
  filterBadge: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
  filterCount: { fontSize: 9, fontWeight: "700" as const },
  listHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingHorizontal: 16, paddingVertical: 8, borderBottomWidth: 1 },
  listHeaderTip: { fontSize: 10, fontStyle: "italic" },
  listHeaderCount: { fontSize: 10, fontWeight: "700" as const, letterSpacing: 0.5 },
  empty: { margin: 24, borderRadius: 14, borderWidth: 1, padding: 32, alignItems: "center", gap: 12 },
  emptyLine1: { fontSize: 15, fontWeight: "700" as const },
  emptyLine2: { fontSize: 12, textAlign: "center" as const, lineHeight: 18 },
  listEmpty: { flex: 1 },
});
