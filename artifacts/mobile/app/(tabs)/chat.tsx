import { Feather } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Linking,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { KeyboardAvoidingView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { getApiBase, safeJson } from "@/constants/api";
import { useBotContext } from "@/context/BotContext";
import { useColors } from "@/hooks/useColors";
import type { ChatMessage } from "@/types";

const PROVIDER_LABEL: Record<string, string> = {
  gemini:       "Gemini",
  openai:       "OpenAI",
  claude:       "Claude",
  grok:         "Grok",
  groq:         "Groq",
  custom:       "Custom AI",
  "rule-based": "Rule-based",
};

const QUICK_TOPICS = [
  { icon: "trending-up",  label: "أداء البوت",       msg: "كيف يعمل البوت الآن؟ اعطني تقرير الأداء كاملاً" },
  { icon: "globe",        label: "أخبار السوق",       msg: "ما أهم أخبار العملات الرقمية اليوم؟" },
  { icon: "cpu",          label: "استراتيجية AI",     msg: "ما الاستراتيجية التي يستخدمها البوت حالياً وكيف يتخذ قراراته؟" },
  { icon: "shield",       label: "تداول حلال",        msg: "اشرح لي مبادئ التداول الإسلامي الحلال وكيف يلتزم بها البوت" },
  { icon: "activity",     label: "RSI & MACD",        msg: "Explain RSI divergence and MACD crossover signals with examples." },
  { icon: "bar-chart-2",  label: "إدارة المخاطر",     msg: "كيف أدير المخاطر في التداول؟ اشرح قاعدة 1.5%" },
];

const GENERAL_TOPICS = [
  { icon: "newspaper",   label: "أخبار عالمية",     msg: "ما أهم الأخبار العالمية الآن؟" },
  { icon: "bitcoin",     label: "Bitcoin تحليل",    msg: "حلل وضع Bitcoin الحالي وهل هو وقت شراء مناسب؟" },
  { icon: "book",        label: "تعلم معي",          msg: "علمني شيئاً مفيداً عن الاستثمار والتداول للمبتدئين" },
  { icon: "zap",         label: "نصيحة سريعة",       msg: "اعطني نصيحة استثمارية مفيدة اليوم" },
  { icon: "help-circle", label: "اسأل أي شيء",      msg: "ما هو الفرق بين Spot Trading و Futures؟" },
  { icon: "sun",         label: "موضوع حر",          msg: "حدثني عن أحدث التطورات في عالم الذكاء الاصطناعي" },
];

function makeId() {
  return Date.now().toString() + Math.random().toString(36).slice(2, 9);
}

const WELCOME_MSG: ChatMessage = {
  id: "welcome",
  role: "assistant",
  content:
    "أنا الذكاء الاصطناعي الذي يشغّل روبوت التداول — أحلّل الأسواق وأفتح الصفقات وأتعلم من كل نتيجة.\n\nاسألني عن:\n• صفقاتي الحالية وسبب فتحها\n• أداء المحفظة والإحصاءات\n• تحليل أي عملة رقمية\n• أخبار السوق أو أي موضوع آخر\n\nتحدث معي بالعربية أو الإنجليزية!",
  timestamp: new Date().toISOString(),
};

export default function ChatScreen() {
  const colors    = useColors();
  const insets    = useSafeAreaInsets();
  const { autoExplain, clearAutoExplain } = useBotContext();

  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME_MSG]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [activeProvider, setActiveProvider] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"trading" | "general">("trading");
  const inputRef = useRef<TextInput>(null);
  const listRef = useRef<FlatList>(null);

  const topPad = Platform.OS === "web" ? 67 : insets.top;
  const bottomPad = Platform.OS === "web" ? 90 : insets.bottom;

  // ── Auto-explain: when a trade closes, AI sends an automatic explanation ──
  const seenExplainId = useRef<string | null>(null);
  useEffect(() => {
    if (!autoExplain || autoExplain.id === seenExplainId.current) return;
    seenExplainId.current = autoExplain.id;
    const headerLine = autoExplain.isWin
      ? `✅ تحليل الصفقة الرابحة\n${autoExplain.tradeInfo}`
      : `🔴 تحليل الصفقة الخاسرة\n${autoExplain.tradeInfo}`;
    const explainMsg: ChatMessage = {
      id: `explain_${autoExplain.id}`,
      role: "assistant",
      content: `${headerLine}\n\n${autoExplain.text}`,
      timestamp: new Date().toISOString(),
      provider: autoExplain.provider,
    };
    setMessages((prev) => [explainMsg, ...prev]);
    clearAutoExplain();
  }, [autoExplain, clearAutoExplain]);

  // ── Load conversation history from DB on mount ────────────────────────────
  // Filter out old "no AI provider" warning messages from history
  const NO_AI_PATTERNS = ["لا يوجد مزود AI", "No AI", "أضف مفتاح API من صفحة **CONFIG**"];
  const isNoAiWarning = (content: string) =>
    NO_AI_PATTERNS.some((p) => content.includes(p));

  useEffect(() => {
    (async () => {
      try {
        const r = await fetch(`${getApiBase()}/conversations?screen=chat&limit=80`);
        if (r.ok) {
          const d = await safeJson(r);
          if (d?.messages && d.messages.length > 0) {
            const hist: ChatMessage[] = d.messages
              .filter((m: any) => !(m.role === "assistant" && isNoAiWarning(m.content ?? "")))
              .map((m: any) => ({
                id: m.id ?? makeId(),
                role: m.role as "user" | "assistant",
                content: m.content,
                timestamp: m.created_at ?? new Date().toISOString(),
                provider: m.provider || undefined,
              }));
            setMessages([WELCOME_MSG, ...hist]);
          }
        }
      } catch { /* ignore */ }
      setHistoryLoading(false);
    })();
  }, []);

  const loadProvider = useCallback(async () => {
    try {
      const r = await fetch(`${getApiBase()}/ai/providers`);
      if (r.ok) {
        const d = await safeJson(r);
        setActiveProvider(d?.active_provider ?? null);
      }
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    loadProvider();
    const t = setInterval(loadProvider, 30_000);
    return () => clearInterval(t);
  }, [loadProvider]);

  const sendMessage = async (text?: string) => {
    const message = (text ?? input).trim();
    if (!message || loading) return;

    setInput("");
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);

    const userMsg: ChatMessage = {
      id: makeId(),
      role: "user",
      content: message,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [userMsg, ...prev]);
    setLoading(true);

    try {
      const res = await fetch(`${getApiBase()}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });
      const data = await safeJson(res);
      if (data?.provider && data.provider !== "rule-based") {
        setActiveProvider(data.provider);
      }
      const botMsg: ChatMessage = {
        id: makeId(),
        role: "assistant",
        content: data.response ?? "لم يتم استلام رد.",
        timestamp: new Date().toISOString(),
        provider: data.provider ?? "rule-based",
        key: data.key,
      };
      setMessages((prev) => [botMsg, ...prev]);
    } catch {
      const errMsg: ChatMessage = {
        id: makeId(),
        role: "assistant",
        content:
          "⚠️ لا يمكن الاتصال بالخادم. تأكد من أن البوت يعمل وأن مفتاح AI مضبوط في الإعدادات.",
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [errMsg, ...prev]);
    } finally {
      setLoading(false);
    }
  };

  const providerLabel = activeProvider ? PROVIDER_LABEL[activeProvider] ?? activeProvider : "No AI";
  const providerColor = activeProvider && activeProvider !== "rule-based" ? colors.primary : (colors.warning ?? "#FF9F43");
  const topics = activeTab === "trading" ? QUICK_TOPICS : GENERAL_TOPICS;

  return (
    <KeyboardAvoidingView
      style={[styles.root, { backgroundColor: colors.background }]}
      behavior={Platform.OS === "ios" ? "padding" : "height"}
      keyboardVerticalOffset={0}
    >
      {/* Header */}
      <View style={[styles.header, { paddingTop: topPad + 8, backgroundColor: colors.background, borderBottomColor: colors.border }]}>
        <View style={styles.headerLeft}>
          <View style={[styles.avatarDot, { backgroundColor: `${providerColor}22` }]}>
            <Feather name="cpu" size={12} color={providerColor} />
          </View>
          <View>
            <Text style={[styles.title, { color: colors.foreground }]}>AI Tutor</Text>
            <View style={styles.subtitleRow}>
              <View style={[styles.providerDot, { backgroundColor: providerColor }]} />
              <Text style={[styles.subtitle, { color: colors.mutedForeground }]}>
                {providerLabel} • مساعد ذكي شامل
              </Text>
            </View>
          </View>
        </View>
        <Pressable
          style={[styles.newsBtn, { borderColor: colors.border, backgroundColor: colors.card }]}
          onPress={() => sendMessage("ما أهم أخبار العملات الرقمية والأسواق المالية الآن؟")}
        >
          <Feather name="rss" size={13} color={colors.primary} />
          <Text style={[styles.newsBtnTxt, { color: colors.primary }]}>أخبار</Text>
        </Pressable>
      </View>

      {/* No-AI Banner — shown once at top, not in every message */}
      {(!activeProvider || activeProvider === "rule-based") && !historyLoading && (
        <Pressable
          style={[styles.noAiBanner, { backgroundColor: "#FF9F4318", borderColor: "#FF9F4340" }]}
          onPress={() => Linking.openURL("https://aistudio.google.com/app/apikey")}
        >
          <Feather name="key" size={13} color="#FF9F43" />
          <Text style={styles.noAiBannerTxt}>
            لم تُضف مفتاح AI بعد — اضغط هنا للحصول على Gemini مجاناً
          </Text>
          <Feather name="external-link" size={11} color="#FF9F43" />
        </Pressable>
      )}

      {/* Message list */}
      <FlatList
        ref={listRef}
        data={messages}
        inverted
        keyExtractor={(m) => m.id}
        keyboardDismissMode="interactive"
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
        contentContainerStyle={[styles.messageList, { paddingBottom: 12 }]}
        ListHeaderComponent={
          loading ? (
            <View style={[styles.bubble, styles.botBubble, { backgroundColor: colors.card, borderColor: colors.border }]}>
              <View style={styles.typingRow}>
                <ActivityIndicator size="small" color={colors.primary} />
                <Text style={[styles.typingText, { color: colors.mutedForeground }]}>
                  {providerLabel} يفكر...
                </Text>
              </View>
            </View>
          ) : null
        }
        renderItem={({ item }) => {
          const msgProviderColor =
            item.provider === "gemini"    ? "#4285F4"
            : item.provider === "openai"  ? "#10A37F"
            : item.provider === "claude"  ? "#C9642A"
            : item.provider === "rule-based" ? "#888"
            : providerColor;
          const msgProviderLabel =
            item.provider === "gemini"    ? "Gemini"
            : item.provider === "openai"  ? "OpenAI"
            : item.provider === "claude"  ? "Claude"
            : item.provider === "rule-based" ? "Rule-Based"
            : null;
          return (
            <View style={[styles.bubbleWrapper, item.role === "user" ? styles.userWrapper : styles.botWrapper]}>
              {item.role === "assistant" && (
                <View style={[styles.assistantAvatar, { backgroundColor: `${msgProviderColor}22` }]}>
                  <Feather name="cpu" size={10} color={msgProviderColor} />
                </View>
              )}
              <View style={{ maxWidth: "82%", alignItems: item.role === "user" ? "flex-end" : "flex-start" }}>
                <View style={[
                  styles.bubble,
                  item.role === "user"
                    ? [styles.userBubble, { backgroundColor: colors.primary }]
                    : [styles.botBubble, { backgroundColor: colors.card, borderColor: colors.border }],
                ]}>
                  <Text style={[styles.bubbleText, { color: item.role === "user" ? colors.primaryForeground : colors.foreground }]}>
                    {item.content}
                  </Text>
                </View>
                {item.role === "assistant" && msgProviderLabel && (
                  <View style={{ flexDirection: "row", alignItems: "center", gap: 4, marginTop: 3, marginLeft: 4 }}>
                    <View style={{ width: 5, height: 5, borderRadius: 2.5, backgroundColor: msgProviderColor }} />
                    <Text style={{ fontSize: 9, color: msgProviderColor, fontWeight: "700", letterSpacing: 0.5 }}>
                      {msgProviderLabel}
                    </Text>
                  </View>
                )}
              </View>
            </View>
          );
        }}
      />

      {/* Quick prompts */}
      {messages.length <= 1 && (
        <View style={styles.quickSection}>
          <View style={[styles.tabRow, { borderBottomColor: colors.border }]}>
            {(["trading", "general"] as const).map((tab) => (
              <Pressable
                key={tab}
                onPress={() => setActiveTab(tab)}
                style={[styles.tabBtn, { borderBottomColor: activeTab === tab ? colors.primary : "transparent" }]}
              >
                <Text style={[styles.tabText, { color: activeTab === tab ? colors.primary : colors.mutedForeground }]}>
                  {tab === "trading" ? "📊 تداول" : "🌐 عام"}
                </Text>
              </Pressable>
            ))}
          </View>

          <View style={styles.lessonGrid}>
            {topics.map((t) => (
              <Pressable
                key={t.label}
                onPress={() => sendMessage(t.msg)}
                style={[styles.lessonCard, { backgroundColor: colors.card, borderColor: colors.border }]}
              >
                <View style={[styles.lessonIcon, { backgroundColor: `${colors.primary}18` }]}>
                  <Feather name={t.icon as any} size={14} color={colors.primary} />
                </View>
                <Text style={[styles.lessonLabel, { color: colors.foreground }]}>{t.label}</Text>
              </Pressable>
            ))}
          </View>
        </View>
      )}

      {/* Input bar */}
      <View style={[styles.inputRow, { backgroundColor: colors.background, borderTopColor: colors.border, paddingBottom: bottomPad + 8 }]}>
        <TextInput
          ref={inputRef}
          style={[styles.input, { backgroundColor: colors.card, color: colors.foreground, borderColor: colors.border }]}
          placeholder="اسألني عن أي موضوع..."
          placeholderTextColor={colors.mutedForeground}
          value={input}
          onChangeText={setInput}
          multiline
          returnKeyType="send"
          blurOnSubmit
          onSubmitEditing={() => sendMessage()}
        />
        <Pressable
          onPress={() => sendMessage()}
          disabled={!input.trim() || loading}
          style={[styles.sendBtn, { backgroundColor: input.trim() && !loading ? colors.primary : colors.muted }]}
        >
          <Feather name="send" size={18} color={input.trim() && !loading ? colors.primaryForeground : colors.mutedForeground} />
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  header: {
    paddingHorizontal: 20, paddingBottom: 14, borderBottomWidth: 1,
    flexDirection: "row", alignItems: "flex-end", justifyContent: "space-between",
  },
  headerLeft: { flexDirection: "row", alignItems: "center", gap: 10 },
  avatarDot: { width: 32, height: 32, borderRadius: 10, alignItems: "center", justifyContent: "center" },
  title:    { fontSize: 22, fontWeight: "700" as const, letterSpacing: -0.5 },
  subtitleRow: { flexDirection: "row", alignItems: "center", gap: 5, marginTop: 1 },
  providerDot: { width: 6, height: 6, borderRadius: 3 },
  subtitle: { fontSize: 11 },
  newsBtn: { flexDirection: "row", alignItems: "center", gap: 5, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 10, borderWidth: 1 },
  newsBtnTxt: { fontSize: 12, fontWeight: "600" as const },
  messageList: { paddingHorizontal: 16, paddingTop: 12, gap: 10 },
  bubbleWrapper: { marginBottom: 8 },
  userWrapper: { alignItems: "flex-end" },
  botWrapper: { alignItems: "flex-start", flexDirection: "row", gap: 8 },
  assistantAvatar: { width: 22, height: 22, borderRadius: 6, alignItems: "center", justifyContent: "center", marginTop: 4, flexShrink: 0 },
  bubble: { maxWidth: "82%", paddingHorizontal: 14, paddingVertical: 10, borderRadius: 16 },
  userBubble: { borderBottomRightRadius: 4 },
  botBubble: { borderWidth: 1, borderBottomLeftRadius: 4 },
  bubbleText: { fontSize: 14, lineHeight: 21 },
  typingRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  typingText: { fontSize: 12 },
  quickSection: { flexShrink: 0 },
  tabRow: { flexDirection: "row", borderBottomWidth: 1, paddingHorizontal: 16 },
  tabBtn: { flex: 1, paddingVertical: 10, alignItems: "center", borderBottomWidth: 2 },
  tabText: { fontSize: 13, fontWeight: "600" as const },
  lessonGrid: { flexDirection: "row", flexWrap: "wrap", paddingHorizontal: 12, paddingVertical: 10, gap: 8 },
  lessonCard: { flexDirection: "row", alignItems: "center", gap: 8, paddingHorizontal: 12, paddingVertical: 9, borderRadius: 10, borderWidth: 1, width: "47%" },
  lessonIcon: { width: 26, height: 26, borderRadius: 7, alignItems: "center", justifyContent: "center" },
  lessonLabel: { fontSize: 12, fontWeight: "500" as const, flex: 1 },
  inputRow: { flexDirection: "row", alignItems: "flex-end", gap: 10, paddingHorizontal: 16, paddingTop: 10, borderTopWidth: 1 },
  input: { flex: 1, borderRadius: 20, borderWidth: 1, paddingHorizontal: 16, paddingVertical: 10, fontSize: 14, maxHeight: 100 },
  sendBtn: { width: 42, height: 42, borderRadius: 21, alignItems: "center", justifyContent: "center" },
  noAiBanner: {
    flexDirection: "row" as const, alignItems: "center", gap: 8,
    paddingHorizontal: 14, paddingVertical: 9, borderBottomWidth: 1,
  },
  noAiBannerTxt: { flex: 1, fontSize: 12, color: "#FF9F43", fontWeight: "500" as const },
});
