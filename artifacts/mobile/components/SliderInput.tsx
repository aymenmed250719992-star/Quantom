import React, { useCallback, useRef, useState } from "react";
import { LayoutChangeEvent, PanResponder, StyleSheet, Text, View } from "react-native";

import { useColors } from "@/hooks/useColors";

interface SliderInputProps {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  suffix?: string;
  onValueChange: (v: number) => void;
}

export function SliderInput({
  label,
  value,
  min,
  max,
  step,
  suffix = "",
  onValueChange,
}: SliderInputProps) {
  const colors = useColors();
  const [trackWidth, setTrackWidth] = useState(0);
  const trackRef = useRef<View>(null);

  const clamp = useCallback(
    (v: number) => {
      const snapped = Math.round(v / step) * step;
      return Math.min(max, Math.max(min, parseFloat(snapped.toFixed(10))));
    },
    [min, max, step]
  );

  const fillPercent = ((value - min) / (max - min)) * 100;

  const handleLayout = (e: LayoutChangeEvent) => {
    setTrackWidth(e.nativeEvent.layout.width);
  };

  const panResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: () => true,
      onPanResponderGrant: (e) => {
        if (trackWidth > 0) {
          const ratio = Math.max(0, Math.min(1, e.nativeEvent.locationX / trackWidth));
          onValueChange(clamp(min + ratio * (max - min)));
        }
      },
      onPanResponderMove: (e) => {
        if (trackWidth > 0) {
          const ratio = Math.max(0, Math.min(1, e.nativeEvent.locationX / trackWidth));
          onValueChange(clamp(min + ratio * (max - min)));
        }
      },
    })
  ).current;

  return (
    <View style={styles.container}>
      <View style={styles.labelRow}>
        <Text style={[styles.label, { color: colors.mutedForeground }]}>{label}</Text>
        <Text style={[styles.valueText, { color: colors.primary }]}>
          {typeof value === "number" && !Number.isInteger(value)
            ? value.toFixed(1)
            : value}
          {suffix}
        </Text>
      </View>
      <View
        ref={trackRef}
        onLayout={handleLayout}
        style={[styles.track, { backgroundColor: colors.secondary }]}
        {...panResponder.panHandlers}
      >
        <View
          style={[
            styles.fill,
            { width: `${fillPercent}%` as any, backgroundColor: colors.primary },
          ]}
        />
        <View
          style={[
            styles.thumb,
            {
              left: `${fillPercent}%` as any,
              backgroundColor: colors.primary,
              borderColor: colors.background,
            },
          ]}
        />
      </View>
      <View style={styles.rangeRow}>
        <Text style={[styles.rangeText, { color: colors.mutedForeground }]}>
          {min}{suffix}
        </Text>
        <Text style={[styles.rangeText, { color: colors.mutedForeground }]}>
          {max}{suffix}
        </Text>
      </View>
    </View>
  );
}

const THUMB_SIZE = 22;

const styles = StyleSheet.create({
  container: {
    marginBottom: 24,
  },
  labelRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 12,
  },
  label: {
    fontSize: 14,
  },
  valueText: {
    fontSize: 16,
    fontWeight: "700" as const,
  },
  track: {
    height: 4,
    borderRadius: 2,
    position: "relative",
    justifyContent: "center",
  },
  fill: {
    height: 4,
    borderRadius: 2,
    position: "absolute",
    left: 0,
    top: 0,
  },
  thumb: {
    position: "absolute",
    width: THUMB_SIZE,
    height: THUMB_SIZE,
    borderRadius: THUMB_SIZE / 2,
    borderWidth: 3,
    marginLeft: -THUMB_SIZE / 2,
    top: -(THUMB_SIZE / 2 - 2),
  },
  rangeRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginTop: 8,
  },
  rangeText: {
    fontSize: 11,
  },
});
