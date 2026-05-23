import { Feather } from "@expo/vector-icons";
import React from "react";
import { FlatList, Pressable, StyleSheet, Text, View } from "react-native";

import { useColors } from "@/hooks/useColors";

interface LogFeedProps {
  logs: string[];
  onClear?: () => void;
  maxHeight?: number;
}

function getLogStyle(log: string, colors: ReturnType<typeof useColors>) {
  if (log.includes("❌") || log.toLowerCase().includes("error")) {
    return { color: colors.destructive, prefix: "ERR", prefixColor: colors.destructive };
  }
  if (log.includes("🚫") || log.toLowerCase().includes("violation")) {
    return { color: "#FF6B6B", prefix: "BLK", prefixColor: "#FF6B6B" };
  }
  if (log.includes("✅") || log.includes("BUY") || log.includes("SELL")) {
    return { color: colors.primary, prefix: "TRD", prefixColor: colors.primary };
  }
  if (log.includes("🟢") || log.includes("started")) {
    return { color: colors.primary, prefix: "SYS", prefixColor: colors.primary };
  }
  if (log.includes("🔴") || log.includes("stopped")) {
    return { color: colors.destructive, prefix: "SYS", prefixColor: colors.destructive };
  }
  if (log.includes("⚡") || log.includes("Adaptive")) {
    return { color: colors.cyan ?? "#00D4FF", prefix: "ADP", prefixColor: colors.cyan ?? "#00D4FF" };
  }
  if (log.includes("🤖") || log.includes("signal") || log.includes("conf:")) {
    return { color: colors.purple ?? "#A855F7", prefix: "AI ", prefixColor: colors.purple ?? "#A855F7" };
  }
  if (log.includes("⚠️")) {
    return { color: colors.warning, prefix: "WRN", prefixColor: colors.warning };
  }
  if (log.includes("🔍") || log.includes("scan") || log.includes("Scan")) {
    return { color: colors.cyan ?? "#00D4FF", prefix: "SCN", prefixColor: colors.cyan ?? "#00D4FF" };
  }
  return { color: "#3A5A78", prefix: "LOG", prefixColor: "#3A5A78" };
}

function timestamp(): string {
  return new Date().toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function LogFeed({ logs, onClear, maxHeight = 220 }: LogFeedProps) {
  const colors = useColors();

  return (
    <View style={[styles.container, { backgroundColor: "#060E1E", borderColor: colors.border, maxHeight }]}>
      {/* Terminal header bar */}
      <View style={[styles.termBar, { borderBottomColor: colors.border }]}>
        <View style={styles.termDots}>
          <View style={[styles.termDot, { backgroundColor: "#FF5F57" }]} />
          <View style={[styles.termDot, { backgroundColor: "#FFBD2E" }]} />
          <View style={[styles.termDot, { backgroundColor: "#28C840" }]} />
        </View>
        <Text style={[styles.termTitle, { color: colors.mutedForeground }]}>
          LIVE SCANNER FEED
        </Text>
        <Pressable onPress={onClear} hitSlop={8}>
          <Text style={[styles.clearBtn, { color: colors.mutedForeground }]}>CLR</Text>
        </Pressable>
      </View>

      {logs.length === 0 ? (
        <View style={styles.empty}>
          <Text style={[styles.emptyText, { color: "#1E3A5A" }]}>
            {'> '}awaiting signals...
          </Text>
        </View>
      ) : (
        <FlatList
          data={logs}
          keyExtractor={(_, i) => String(i)}
          showsVerticalScrollIndicator={false}
          contentContainerStyle={styles.list}
          renderItem={({ item }) => {
            const style = getLogStyle(item, colors);
            return (
              <View style={styles.logRow}>
                <Text style={[styles.logPrefix, { color: style.prefixColor }]}>
                  {style.prefix}
                </Text>
                <Text style={styles.logSep}>│</Text>
                <Text
                  style={[styles.logText, { color: style.color }]}
                  numberOfLines={2}
                >
                  {item.replace(/[🤖✅❌⚠️🚫🟢🔴🔍⚡💡📊]/gu, "").trim()}
                </Text>
              </View>
            );
          }}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    borderRadius: 10,
    borderWidth: 1,
    overflow: "hidden",
  },
  termBar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderBottomWidth: 1,
  },
  termDots: { flexDirection: "row", gap: 5 },
  termDot: { width: 8, height: 8, borderRadius: 4 },
  termTitle: {
    fontSize: 9,
    fontFamily: "monospace",
    letterSpacing: 2,
    fontWeight: "600" as const,
  },
  clearBtn: { fontSize: 9, fontFamily: "monospace", letterSpacing: 1 },
  empty: { padding: 14 },
  emptyText: {
    fontSize: 11,
    fontFamily: "monospace",
  },
  list: { padding: 8, gap: 3 },
  logRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 6,
  },
  logPrefix: {
    fontSize: 9,
    fontFamily: "monospace",
    fontWeight: "700" as const,
    letterSpacing: 0.5,
    minWidth: 24,
    paddingTop: 1,
  },
  logSep: {
    fontSize: 10,
    fontFamily: "monospace",
    color: "#1E3A5A",
    paddingTop: 1,
  },
  logText: {
    fontSize: 10,
    fontFamily: "monospace",
    flex: 1,
    lineHeight: 15,
  },
});
