import React from "react";
import { StyleSheet, Text, View } from "react-native";

import { useColors } from "@/hooks/useColors";

interface StatCardProps {
  label: string;
  value: string;
  subValue?: string;
  accent?: boolean;
  danger?: boolean;
  warning?: boolean;
}

export function StatCard({ label, value, subValue, accent, danger, warning }: StatCardProps) {
  const colors = useColors();

  const valueColor = danger
    ? colors.destructive
    : warning
    ? colors.warning
    : accent
    ? colors.primary
    : colors.foreground;

  const borderColor = danger
    ? `${colors.destructive}22`
    : accent
    ? `${colors.primary}22`
    : colors.border;

  return (
    <View
      style={[
        styles.card,
        {
          backgroundColor: colors.card,
          borderColor,
        },
      ]}
    >
      <Text style={[styles.label, { color: colors.mutedForeground }]}>{label}</Text>
      <Text style={[styles.value, { color: valueColor }]}>{value}</Text>
      {subValue ? (
        <Text style={[styles.subValue, { color: colors.mutedForeground }]}>{subValue}</Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    flex: 1,
    borderRadius: 10,
    borderWidth: 1,
    padding: 14,
    minWidth: 90,
  },
  label: {
    fontSize: 9,
    letterSpacing: 1.2,
    marginBottom: 8,
    fontWeight: "600" as const,
    textTransform: "uppercase" as const,
  },
  value: {
    fontSize: 20,
    fontWeight: "700" as const,
    fontFamily: "monospace",
    letterSpacing: -0.5,
  },
  subValue: {
    fontSize: 10,
    marginTop: 4,
    fontFamily: "monospace",
  },
});
