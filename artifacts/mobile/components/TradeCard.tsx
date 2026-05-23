import { Feather } from "@expo/vector-icons";
import React from "react";
import { StyleSheet, Text, View } from "react-native";

import { useColors } from "@/hooks/useColors";
import type { Trade } from "@/types";

interface TradeCardProps {
  trade: Trade;
  compact?: boolean;
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
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export function TradeCard({ trade, compact = false }: TradeCardProps) {
  const colors = useColors();
  const isBuy = trade.side === "buy";
  const isOpen = trade.status === "open";
  const isWin = (trade.pnl ?? 0) > 0;
  const pnlPct = calcPnlPct(trade);
  const pnl = trade.pnl ?? 0;

  const sideColor = isBuy ? colors.primary : colors.destructive;
  const pnlColor = isOpen ? colors.mutedForeground : isWin ? colors.primary : colors.destructive;

  return (
    <View
      style={[
        styles.card,
        {
          backgroundColor: colors.card,
          borderColor: isOpen
            ? `${colors.cyan ?? "#00D4FF"}33`
            : isWin
            ? `${colors.primary}22`
            : `${colors.destructive}18`,
          borderLeftColor: isOpen
            ? colors.cyan ?? "#00D4FF"
            : isWin
            ? colors.primary
            : colors.destructive,
        },
      ]}
    >
      <View style={styles.top}>
        {/* Side pill */}
        <View style={[styles.sidePill, { backgroundColor: `${sideColor}18`, borderColor: `${sideColor}44` }]}>
          <Feather name={isBuy ? "arrow-up" : "arrow-down"} size={10} color={sideColor} />
          <Text style={[styles.sideText, { color: sideColor }]}>
            {isBuy ? "BUY" : "SELL"}
          </Text>
        </View>

        <Text style={[styles.symbol, { color: colors.foreground }]}>{trade.symbol}</Text>

        <View style={styles.topRight}>
          {/* Status */}
          {isOpen ? (
            <View style={[styles.openBadge, { backgroundColor: `${colors.cyan ?? "#00D4FF"}18`, borderColor: `${colors.cyan ?? "#00D4FF"}44` }]}>
              <View style={[styles.openDot, { backgroundColor: colors.cyan ?? "#00D4FF" }]} />
              <Text style={[styles.openText, { color: colors.cyan ?? "#00D4FF" }]}>OPEN</Text>
            </View>
          ) : (
            <View style={[styles.closedBadge, { backgroundColor: isWin ? `${colors.primary}15` : `${colors.destructive}15` }]}>
              <Text style={[styles.closedText, { color: isWin ? colors.primary : colors.destructive }]}>
                {isWin ? "WIN" : "LOSS"}
              </Text>
            </View>
          )}
          <Text style={[styles.timeText, { color: colors.mutedForeground }]}>
            {timeAgo(trade.created_at)}
          </Text>
        </View>
      </View>

      <View style={styles.bottom}>
        {/* Price info */}
        <View style={styles.priceBlock}>
          <Text style={[styles.priceLabel, { color: colors.mutedForeground }]}>ENTRY</Text>
          <Text style={[styles.priceVal, { color: colors.foreground }]}>
            ${trade.entry_price.toFixed(4)}
          </Text>
        </View>

        {!isOpen && trade.exit_price ? (
          <>
            <Feather name="chevron-right" size={12} color={colors.mutedForeground} />
            <View style={styles.priceBlock}>
              <Text style={[styles.priceLabel, { color: colors.mutedForeground }]}>EXIT</Text>
              <Text style={[styles.priceVal, { color: colors.foreground }]}>
                ${trade.exit_price.toFixed(4)}
              </Text>
            </View>
          </>
        ) : null}

        <View style={{ flex: 1 }} />

        {/* PnL */}
        <View style={styles.pnlBlock}>
          <Text style={[styles.pnlAmount, { color: pnlColor }]}>
            {isOpen ? "—" : `${pnl >= 0 ? "+" : ""}$${Math.abs(pnl).toFixed(4)}`}
          </Text>
          {!isOpen && pnlPct != null && (
            <View style={[styles.pnlPctBadge, { backgroundColor: `${pnlColor}18` }]}>
              <Text style={[styles.pnlPctText, { color: pnlColor }]}>
                {pnlPct >= 0 ? "+" : ""}{pnlPct.toFixed(2)}%
              </Text>
            </View>
          )}
        </View>
      </View>

      {!compact && (
        <View style={[styles.footer, { borderTopColor: colors.border }]}>
          <Text style={[styles.footerItem, { color: colors.mutedForeground }]}>
            <Text style={{ color: "#3A5A78" }}>AI </Text>
            {trade.ai_confidence}%
          </Text>
          <Text style={[styles.footerItem, { color: colors.mutedForeground }]}>
            <Text style={{ color: "#3A5A78" }}>QTY </Text>
            {trade.quantity.toFixed(6)}
          </Text>
          {trade.pattern ? (
            <Text style={[styles.footerItem, { color: colors.purple ?? "#A855F7" }]}>
              ◆ {trade.pattern}
            </Text>
          ) : null}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: 10,
    borderWidth: 1,
    borderLeftWidth: 3,
    marginHorizontal: 16,
    marginBottom: 6,
    overflow: "hidden",
  },
  top: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    padding: 12,
    paddingBottom: 8,
  },
  sidePill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 3,
    paddingHorizontal: 7,
    paddingVertical: 3,
    borderRadius: 5,
    borderWidth: 1,
  },
  sideText: { fontSize: 9, fontWeight: "800" as const, letterSpacing: 0.8 },
  symbol: { fontSize: 14, fontWeight: "700" as const, fontFamily: "monospace" },
  topRight: { marginLeft: "auto", alignItems: "flex-end", gap: 2 },
  openBadge: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
    borderWidth: 1,
  },
  openDot: { width: 4, height: 4, borderRadius: 2 },
  openText: { fontSize: 8, fontWeight: "700" as const, letterSpacing: 0.5 },
  closedBadge: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  closedText: { fontSize: 9, fontWeight: "700" as const, letterSpacing: 0.5 },
  timeText: { fontSize: 9, fontFamily: "monospace" },
  bottom: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: 12,
    paddingBottom: 10,
  },
  priceBlock: {},
  priceLabel: { fontSize: 8, letterSpacing: 0.8, fontWeight: "600" as const },
  priceVal: { fontSize: 11, fontFamily: "monospace", fontWeight: "600" as const },
  pnlBlock: { alignItems: "flex-end", gap: 3 },
  pnlAmount: { fontSize: 14, fontWeight: "700" as const, fontFamily: "monospace" },
  pnlPctBadge: { paddingHorizontal: 5, paddingVertical: 1, borderRadius: 4 },
  pnlPctText: { fontSize: 10, fontWeight: "700" as const, fontFamily: "monospace" },
  footer: {
    flexDirection: "row",
    gap: 16,
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderTopWidth: 1,
  },
  footerItem: { fontSize: 10, fontFamily: "monospace" },
});
