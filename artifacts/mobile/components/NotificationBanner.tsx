/**
 * NotificationBanner — بانر إشعار عائم يظهر في أعلى الشاشة
 * يعمل 100% بدون حزم إضافية — Animated API فقط
 */
import { Feather } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import React, { useEffect, useRef } from "react";
import { Animated, Platform, Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

export type NotifType = "win" | "loss" | "signal" | "alert" | "emergency" | "info";

export interface AppNotification {
  id: string;
  type: NotifType;
  title: string;
  body: string;
}

const CONFIG: Record<NotifType, { bg: string; border: string; icon: string; haptic: "light" | "medium" | "heavy" | "success" | "warning" | "error" }> = {
  win:       { bg: "#0d2b1a", border: "#00D26A", icon: "trending-up",    haptic: "success" },
  loss:      { bg: "#2b0d0d", border: "#FF6B6B", icon: "trending-down",  haptic: "error"   },
  signal:    { bg: "#0d1b2b", border: "#00D4FF", icon: "zap",            haptic: "light"   },
  alert:     { bg: "#2b1f0d", border: "#FF9F43", icon: "alert-triangle", haptic: "warning" },
  emergency: { bg: "#2b0d0d", border: "#FF4757", icon: "shield-off",     haptic: "heavy"   },
  info:      { bg: "#0d0d2b", border: "#A78BFA", icon: "info",           haptic: "light"   },
};

interface Props {
  notification: AppNotification;
  onDismiss: (id: string) => void;
  index: number;
}

export function NotificationBanner({ notification, onDismiss, index }: Props) {
  const insets = useSafeAreaInsets();
  const translateY = useRef(new Animated.Value(-120)).current;
  const opacity    = useRef(new Animated.Value(0)).current;
  const cfg = CONFIG[notification.type] ?? CONFIG.info;

  const topPad = Platform.OS === "web" ? 67 : insets.top;

  useEffect(() => {
    // Fire haptic
    if (notification.type === "win") {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    } else if (notification.type === "loss" || notification.type === "emergency") {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
    } else if (notification.type === "alert") {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
    } else {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    }

    // Slide in
    Animated.parallel([
      Animated.spring(translateY, {
        toValue: 0,
        useNativeDriver: true,
        tension: 80,
        friction: 12,
      }),
      Animated.timing(opacity, {
        toValue: 1,
        duration: 200,
        useNativeDriver: true,
      }),
    ]).start();

    // Auto-dismiss after 4s
    const timer = setTimeout(() => dismiss(), 4000);
    return () => clearTimeout(timer);
  }, []);

  const dismiss = () => {
    Animated.parallel([
      Animated.timing(translateY, { toValue: -120, duration: 280, useNativeDriver: true }),
      Animated.timing(opacity,    { toValue: 0,    duration: 220, useNativeDriver: true }),
    ]).start(() => onDismiss(notification.id));
  };

  const topOffset = topPad + 10 + index * 84;

  return (
    <Animated.View
      style={[
        styles.container,
        { top: topOffset, opacity, transform: [{ translateY }],
          backgroundColor: cfg.bg, borderColor: cfg.border },
      ]}
    >
      <Pressable style={styles.inner} onPress={dismiss}>
        <View style={[styles.iconBox, { backgroundColor: `${cfg.border}22` }]}>
          <Feather name={cfg.icon as any} size={18} color={cfg.border} />
        </View>
        <View style={{ flex: 1, gap: 2 }}>
          <Text style={[styles.title, { color: "#fff" }]} numberOfLines={1}>{notification.title}</Text>
          <Text style={[styles.body,  { color: "#b0b0c0" }]} numberOfLines={2}>{notification.body}</Text>
        </View>
        <View style={[styles.dismissBtn, { backgroundColor: `${cfg.border}18` }]}>
          <Feather name="x" size={12} color={cfg.border} />
        </View>
      </Pressable>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: {
    position: "absolute" as const,
    left: 12, right: 12,
    zIndex: 9999,
    borderRadius: 16,
    borderWidth: 1,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.4,
    shadowRadius: 12,
    elevation: 20,
  },
  inner: {
    flexDirection: "row" as const,
    alignItems: "center" as const,
    gap: 12,
    padding: 14,
  },
  iconBox: {
    width: 40, height: 40, borderRadius: 12,
    alignItems: "center" as const, justifyContent: "center" as const,
    flexShrink: 0,
  },
  title: { fontSize: 13, fontWeight: "700" as const, letterSpacing: -0.2 },
  body:  { fontSize: 11, lineHeight: 16 },
  dismissBtn: { width: 24, height: 24, borderRadius: 12, alignItems: "center" as const, justifyContent: "center" as const, flexShrink: 0 },
});
