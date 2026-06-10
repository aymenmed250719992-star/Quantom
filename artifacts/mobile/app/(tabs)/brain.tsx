/**
 * BRAIN — عقل الأيجنت ولوحة التحكم الكاملة
 * الذاكرة | الاستراتيجية | الدروس المستفادة | صحة AI | تحكم كامل
 */
import { Feather } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Animated,
  FlatList,
  Platform,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  KeyboardAvoidingView,
  TextInput,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import AsyncStorage from "@react-native-async-storage/async-storage";

import { getApiBase, safeJson } from "@/constants/api";
import { useColors } from "@/hooks/useColors";

// ── Local persistence keys ─────────────────────────────────────────────────
const CHAT_STORAGE_KEY   = "quantom_brain_chat_v1";
const MEMORY_BACKUP_KEY  = "quantom_memory_backup_v1";
const MAX_LOCAL_MESSAGES = 200;

// ── Types ─────────────────────────────────────────────────────────────────────

interface BrainMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  provider?: string;
  executed_command?: string | null;
  timestamp: string;
  metadata?: {
    type?: string;    // "trade_auto" | undefined
    event?: string;   // "open" | "close_win" | "close_loss"
    symbol?: string;
    pnl?: number | null;
  };
}

interface AgentMemory {
  strategy: {
    current: string;
    confidence: number;
    goal: string;
    overrides: Record<string, any>;
  };
  streaks: {
    consecutive_wins: number;
    consecutive_losses: number;
    last_results: boolean[];
    emergency_halted: boolean;
  };
  patterns: { pattern: string; win_rate: number; total: number }[];
  recent_thoughts: string[];
  lessons: { lesson: string; symbol: string; outcome: string; created_at: string; market_condition: string }[];
  ai_status: {
    active_provider: string | null;
    available_keys: number;
    total_keys: number;
    keys: {
      provider: string; label: string; available: boolean; exhausted: boolean;
      hours_remaining: number; total_calls: number; success_calls: number;
      failed_calls: number; model_name: string;
    }[];
  };
  settings: {
    target_win_rate: number;
    current_threshold: number;
    reflection_interval_min: number;
  };
}

const STRATEGIES = [
  { id: "mean_reversion",    label: "Mean Rev",    icon: "refresh-cw",  color: "#3B82F6", desc: "شراء عند الانخفاض — كلاسيكي" },
  { id: "trend_following",   label: "Trend",       icon: "trending-up", color: "#10B981", desc: "اتباع الاتجاه الصاعد" },
  { id: "momentum_breakout", label: "Breakout",    icon: "zap",         color: "#F59E0B", desc: "اختراق مستويات القاومة" },
  { id: "scalping",          label: "Scalping",    icon: "fast-forward", color: "#8B5CF6", desc: "صفقات سريعة وصغيرة" },
  { id: "conservative",      label: "Conservative",icon: "shield",      color: "#6B7280", desc: "حماية رأس المال أولاً" },
];

// ── Helper components ─────────────────────────────────────────────────────────

function SectionHeader({ title, icon, color }: { title: string; icon: string; color: string }) {
  const colors = useColors();
  return (
    <View style={sec.row}>
      <View style={[sec.dot, { backgroundColor: color }]} />
      <Text style={[sec.title, { color: colors.mutedForeground }]}>{title}</Text>
    </View>
  );
}
const sec = StyleSheet.create({
  row:   { flexDirection: "row", alignItems: "center", gap: 8, marginBottom: 10, marginTop: 18, marginHorizontal: 16 },
  dot:   { width: 6, height: 6, borderRadius: 3 },
  title: { fontSize: 10, fontWeight: "700", letterSpacing: 1.2, textTransform: "uppercase" },
});

function Card({ children, style }: { children: React.ReactNode; style?: any }) {
  const colors = useColors();
  return (
    <View style={[{ backgroundColor: colors.card, borderRadius: 14, borderWidth: 1, borderColor: colors.border, marginHorizontal: 16, padding: 14 }, style]}>
      {children}
    </View>
  );
}

function ResultDot({ win }: { win: boolean }) {
  return (
    <View style={[rd.dot, { backgroundColor: win ? "#10B981" : "#EF4444" }]} />
  );
}
const rd = StyleSheet.create({ dot: { width: 8, height: 8, borderRadius: 4 } });

const qs = StyleSheet.create({
  btn: { borderRadius: 8, borderWidth: 1, paddingHorizontal: 10, paddingVertical: 5 },
  txt: { fontSize: 11, fontWeight: "600" },
});

const ef = StyleSheet.create({
  scoreCircle:    { width: 64, height: 64, borderRadius: 32, borderWidth: 2.5, alignItems: "center", justifyContent: "center" },
  scoreNum:       { fontSize: 20, fontWeight: "800" },
  scoreMax:       { fontSize: 9,  fontWeight: "600", marginTop: -2 },
  barBg:          { height: 6, borderRadius: 3, overflow: "hidden" },
  barFill:        { height: 6, borderRadius: 3 },
  recTxt:         { fontSize: 12, fontWeight: "700" },
  smallTxt:       { fontSize: 11 },
  factorChip:     { borderRadius: 6, borderWidth: 1, paddingHorizontal: 7, paddingVertical: 3 },
  factorTxt:      { fontSize: 10, fontWeight: "600" },
  consolidateBtn: { flexDirection: "row", alignItems: "center", gap: 6, borderRadius: 8, borderWidth: 1, paddingHorizontal: 10, paddingVertical: 6 },
  consolidateTxt: { fontSize: 12, fontWeight: "700" },
  consolidateMsg: { fontSize: 11, flex: 1 },
});

// ── Main Screen ───────────────────────────────────────────────────────────────

const BRAIN_WELCOME: BrainMessage = {
  id: "brain_welcome",
  role: "assistant",
  content: "مرحباً — أنا عقل البوت. أخبرني ماذا تريد:\n\n• \"غيّر الاستراتيجية إلى Scalping\"\n• \"أوقف البوت\"\n• \"ارفع حد الثقة إلى 70%\"\n• \"ما هي الصفقات الحالية؟\"\n• \"ابدأ واشرح لي منطقك\"\n\nأي سؤال أو أمر — بالعربية أو الإنجليزية!",
  timestamp: new Date().toISOString(),
};

function makeBrainId() {
  return "b_" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
}

const PROVIDER_COLORS: Record<string, string> = {
  gemini: "#4285F4", openai: "#10A37F", claude: "#D97706",
  grok: "#6366F1", custom: "#7C3AED",
};

export default function BrainScreen() {
  const insets = useSafeAreaInsets();
  const colors = useColors();

  const [data, setData]       = useState<AgentMemory | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [cmdLoading, setCmdLoading] = useState<string | null>(null);
  const [msgMap, setMsgMap]   = useState<Record<string, string>>({});
  const [goalInput, setGoalInput]       = useState("");
  const [editGoal, setEditGoal]         = useState(false);

  // ── Efficiency state ──────────────────────────────────────────────────────
  const [efficiency, setEfficiency]         = useState<any>(null);
  const [consolidating, setConsolidating]   = useState(false);
  const [consolidateMsg, setConsolidateMsg] = useState("");

  const loadEfficiency = useCallback(async () => {
    try {
      const r = await fetch(`${getApiBase()}/agent/efficiency`);
      const d = await safeJson(r);
      if (d?.ok) setEfficiency(d);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { loadEfficiency(); }, [loadEfficiency]);

  const handleConsolidate = async () => {
    setConsolidating(true);
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    try {
      const r = await fetch(`${getApiBase()}/agent/consolidate`, { method: "POST" });
      const d = await safeJson(r);
      setConsolidateMsg(d?.summary ?? "تمّ");
      await loadEfficiency();
      setTimeout(() => setConsolidateMsg(""), 4000);
    } catch { setConsolidateMsg("❌ فشل الاتصال"); }
    setConsolidating(false);
  };

  // ── Full memory state ─────────────────────────────────────────────────────
  const [memData, setMemData]           = useState<any>(null);
  const [memSearch, setMemSearch]       = useState("");
  const [memSearchResults, setMemSearchResults] = useState<{ lessons: any[]; knowledge: any[] } | null>(null);
  const [memSearching, setMemSearching] = useState(false);
  const [showAddNote, setShowAddNote]   = useState(false);
  const [noteTitle, setNoteTitle]       = useState("");
  const [noteContent, setNoteContent]   = useState("");
  const [noteCategory, setNoteCategory] = useState("general");
  const [noteSaving, setNoteSaving]     = useState(false);
  const [memTab, setMemTab]             = useState<"lessons"|"knowledge">("lessons");

  // ── Brain Chat state ──────────────────────────────────────────────────────
  const [chatMessages, setChatMessages] = useState<BrainMessage[]>([BRAIN_WELCOME]);
  const [chatInput, setChatInput]       = useState("");
  const [chatLoading, setChatLoading]   = useState(false);
  const chatListRef = useRef<FlatList>(null);
  const bottomPad = Platform.OS === "web" ? 90 : insets.bottom;

  const pulseAnim = useRef(new Animated.Value(1)).current;

  const showMsg = (key: string, msg: string) => {
    setMsgMap(p => ({ ...p, [key]: msg }));
    setTimeout(() => setMsgMap(p => { const n = { ...p }; delete n[key]; return n; }), 3000);
  };

  // ── Save chat messages to phone local storage ─────────────────────────────
  const saveChatLocally = useCallback(async (msgs: BrainMessage[]) => {
    try {
      const toSave = msgs.filter(m => m.id !== "brain_welcome").slice(0, MAX_LOCAL_MESSAGES);
      await AsyncStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(toSave));
    } catch { /* ignore */ }
  }, []);

  // ── Save memory snapshot to phone (backup) ────────────────────────────────
  const backupMemoryLocally = useCallback(async (memSnapshot: any) => {
    try {
      const backup = { ts: new Date().toISOString(), data: memSnapshot };
      await AsyncStorage.setItem(MEMORY_BACKUP_KEY, JSON.stringify(backup));
    } catch { /* ignore */ }
  }, []);

  const load = useCallback(async () => {
    try {
      const r = await fetch(`${getApiBase()}/agent/memory`);
      const d = await safeJson(r);
      if (d) {
        setData(d);
        if (d?.strategy?.goal) setGoalInput(d.strategy.goal);
        backupMemoryLocally(d);
      }
    } catch { /* ignore */ }
    setLoading(false);
    setRefreshing(false);
  }, [backupMemoryLocally]);

  // ── Load brain conversation history: DB first, local fallback ─────────────
  useEffect(() => {
    (async () => {
      // 1. Try local storage first (instant, offline)
      try {
        const local = await AsyncStorage.getItem(CHAT_STORAGE_KEY);
        if (local) {
          const parsed: BrainMessage[] = JSON.parse(local);
          if (parsed.length > 0) {
            setChatMessages([BRAIN_WELCOME, ...parsed]);
          }
        }
      } catch { /* ignore */ }

      // 2. Then try server (richer, more complete)
      try {
        const r = await fetch(`${getApiBase()}/conversations?screen=brain&limit=60`);
        const d = await safeJson(r);
        if (d?.messages?.length > 0) {
          const hist: BrainMessage[] = d.messages.map((m: any) => ({
            id: m.id ?? makeBrainId(),
            role: m.role as "user" | "assistant",
            content: m.content,
            provider: m.provider || undefined,
            executed_command: m.metadata?.executed_command ?? null,
            timestamp: m.created_at ?? new Date().toISOString(),
            metadata: m.metadata ?? undefined,
          }));
          setChatMessages([BRAIN_WELCOME, ...hist]);
          // Mirror server data to local storage
          await saveChatLocally(hist);
        }
      } catch { /* offline — local copy already loaded above */ }
    })();
  }, [saveChatLocally]);

  // ── Quick skill buttons ───────────────────────────────────────────────────
  const QUICK_SKILLS = [
    { label: "📊 محفظتي",      msg: "حلل محفظتي الآن" },
    { label: "📅 تقرير أسبوعي", msg: "أعطني تقرير الأسبوع" },
    { label: "📈 أداء الأنماط", msg: "تقرير أداء الأنماط التقنية" },
    { label: "🛡️ فحص المخاطرة", msg: "فحص مستوى المخاطرة الآن" },
    { label: "🔍 السوق الآن",   msg: "شوف السوق الآن وأسعار BTC و ETH" },
    { label: "🧠 ماذا تعلمت؟",  msg: "ملخص ما تعلمته حتى الآن" },
    { label: "⚖️ قارن الاستراتيجيات", msg: "قارن أداء الاستراتيجيات" },
  ] as const;

  // ── Send message to brain ─────────────────────────────────────────────────
  const sendBrainMessage = async (text?: string) => {
    const message = (text ?? chatInput).trim();
    if (!message || chatLoading) return;
    setChatInput("");
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);

    const userMsg: BrainMessage = {
      id: makeBrainId(),
      role: "user",
      content: message,
      timestamp: new Date().toISOString(),
    };
    setChatMessages(prev => [userMsg, ...prev]);
    setChatLoading(true);

    try {
      const res = await fetch(`${getApiBase()}/brain/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });
      const d = await safeJson(res);
      const botMsg: BrainMessage = {
        id: makeBrainId(),
        role: "assistant",
        content: d?.response ?? "لم يتم استلام رد.",
        provider: d?.provider,
        executed_command: d?.executed_command ?? null,
        timestamp: new Date().toISOString(),
      };
      setChatMessages(prev => {
        const updated = [botMsg, ...prev];
        // Save to phone local storage — learning never lost even offline
        saveChatLocally(updated);
        return updated;
      });
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      if (d?.executed_command) {
        setTimeout(() => load(), 600);
      }
    } catch {
      const errMsg: BrainMessage = {
        id: makeBrainId(),
        role: "assistant",
        content: "⚡ تعذّر الاتصال — الرسائل السابقة محفوظة في هاتفك، التعلّم لم يُفقد.",
        timestamp: new Date().toISOString(),
      };
      setChatMessages(prev => {
        const updated = [errMsg, ...prev];
        saveChatLocally(updated);
        return updated;
      });
    }
    setChatLoading(false);
  };

  useEffect(() => { load(); }, [load]);

  // ── Full memory loader ─────────────────────────────────────────────────────
  const loadMemory = useCallback(async () => {
    try {
      const r = await fetch(`${getApiBase()}/agent/memory/full`);
      const d = await safeJson(r);
      if (d && !d.error) setMemData(d);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { loadMemory(); }, [loadMemory]);

  const handleMemSearch = async (q: string) => {
    setMemSearch(q);
    if (!q.trim()) { setMemSearchResults(null); return; }
    setMemSearching(true);
    try {
      const r = await fetch(`${getApiBase()}/agent/memory/search?q=${encodeURIComponent(q)}`);
      const d = await safeJson(r);
      if (d) setMemSearchResults(d);
    } catch { /* ignore */ }
    setMemSearching(false);
  };

  const handleAddNote = async () => {
    if (!noteTitle.trim() || !noteContent.trim()) return;
    setNoteSaving(true);
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    try {
      const r = await fetch(`${getApiBase()}/agent/knowledge`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: noteTitle.trim(),
          content: noteContent.trim(),
          category: noteCategory,
          importance: 7.0,
          tags: noteCategory,
          source: "user",
        }),
      });
      const d = await safeJson(r);
      if (d?.success) {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        setNoteTitle(""); setNoteContent(""); setShowAddNote(false);
        await loadMemory();
      }
    } catch { /* ignore */ }
    setNoteSaving(false);
  };

  const handleDeleteLesson = async (id: string) => {
    try {
      await fetch(`${getApiBase()}/agent/memory/${id}`, { method: "DELETE" });
      await loadMemory();
    } catch { /* ignore */ }
  };

  const handleDeleteKnowledge = async (id: string) => {
    try {
      await fetch(`${getApiBase()}/agent/knowledge/${id}`, { method: "DELETE" });
      await loadMemory();
    } catch { /* ignore */ }
  };

  // Pulse animation for emergency halt
  useEffect(() => {
    if (data?.streaks?.emergency_halted) {
      Animated.loop(
        Animated.sequence([
          Animated.timing(pulseAnim, { toValue: 0.4, duration: 600, useNativeDriver: true }),
          Animated.timing(pulseAnim, { toValue: 1, duration: 600, useNativeDriver: true }),
        ])
      ).start();
    } else {
      pulseAnim.setValue(1);
    }
  }, [data?.streaks?.emergency_halted]);

  const sendCommand = async (command: string, value?: string, threshold?: number) => {
    setCmdLoading(command + (value ?? ""));
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    try {
      const body: any = { command };
      if (value !== undefined)     body.value = value;
      if (threshold !== undefined) body.threshold = threshold;
      const r = await fetch(`${getApiBase()}/agent/command`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const d = await safeJson(r);
      if (!d) { showMsg(command, "❌ لا يمكن الوصول للسيرفر"); }
      else if (d.success) {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        showMsg(command, `✅ ${d.message ?? "تم"}`);
        await load();
      } else {
        showMsg(command, `❌ ${d.error ?? "خطأ"}`);
      }
    } catch (e: any) {
      showMsg(command, `❌ ${e.message}`);
    }
    setCmdLoading(null);
  };

  const isLoading = (key: string) => cmdLoading === key;

  if (loading) {
    return (
      <View style={[s.center, { backgroundColor: colors.background }]}>
        <ActivityIndicator size="large" color={colors.primary} />
        <Text style={[s.loadTxt, { color: colors.mutedForeground }]}>جارٍ تحميل ذاكرة الأيجنت...</Text>
      </View>
    );
  }

  const st     = data?.strategy;
  const sk     = data?.streaks;
  const ai     = data?.ai_status;
  const cfg    = data?.settings;
  const halted = sk?.emergency_halted ?? false;
  const curStrategy = STRATEGIES.find(s => s.id === (st?.current ?? "mean_reversion")) ?? STRATEGIES[0];

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: colors.background }}
      behavior={Platform.OS === "ios" ? "padding" : "padding"}
      keyboardVerticalOffset={0}
    >
    <ScrollView
      style={{ flex: 1 }}
      contentContainerStyle={{ paddingBottom: 8 }}
      showsVerticalScrollIndicator={false}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={colors.primary} />}
    >
      {/* ── Header ── */}
      <View style={[s.header, { paddingTop: insets.top + 14 }]}>
        <View style={s.headerLeft}>
          <Text style={[s.headerTitle, { color: colors.foreground }]}>AGENT BRAIN</Text>
          <Text style={[s.headerSub, { color: colors.mutedForeground }]}>
            ذاكرة · تحكم · استراتيجية · AI
          </Text>
        </View>
        <Pressable onPress={() => { setRefreshing(true); load(); }} style={[s.refreshBtn, { borderColor: colors.border }]}>
          <Feather name="refresh-cw" size={15} color={colors.mutedForeground} />
        </Pressable>
      </View>

      {/* ── Emergency Halt Banner ── */}
      {halted && (
        <Animated.View style={[s.haltBanner, { opacity: pulseAnim }]}>
          <Feather name="alert-octagon" size={18} color="#EF4444" />
          <View style={{ flex: 1 }}>
            <Text style={s.haltTitle}>الأيجنت متوقف طارئاً</Text>
            <Text style={s.haltSub}>{sk?.consecutive_losses} خسائر متتالية — اضغط "استئناف" للمتابعة</Text>
          </View>
          <Pressable
            style={s.resumeBtn}
            onPress={() => sendCommand("resume")}
            disabled={!!cmdLoading}
          >
            {isLoading("resume") ? <ActivityIndicator size="small" color="#fff" /> : <Text style={s.resumeBtnTxt}>استئناف</Text>}
          </Pressable>
        </Animated.View>
      )}

      {/* ── Efficiency Score Card ── */}
      {efficiency && (() => {
        const sc   = efficiency.score?.score ?? 50;
        const rec  = efficiency.score?.recommendation ?? "";
        const mom  = efficiency.momentum ?? {};
        const trend = efficiency.trend_text ?? "";
        const factors: string[] = efficiency.score?.factors ?? [];
        const scoreColor = sc >= 70 ? "#10B981" : sc >= 50 ? "#F59E0B" : "#EF4444";
        const momEmoji = mom.momentum === "strong_positive" ? "🏆"
                       : mom.momentum === "positive"        ? "✅"
                       : mom.momentum === "negative"        ? "⚠️"
                       : mom.momentum === "strong_negative" ? "🚨" : "❓";
        const dirAr = mom.direction === "rising" ? "📈 متصاعد"
                    : mom.direction === "falling" ? "📉 منحدر"
                    : "➡️ مستقر";
        return (
          <>
            <SectionHeader title="كفاءة البوت التلقائية" icon="activity" color={scoreColor} />
            <Card style={{ gap: 10 }}>
              {/* Score bar */}
              <View style={{ flexDirection: "row", alignItems: "center", gap: 12 }}>
                <View style={[ef.scoreCircle, { borderColor: scoreColor }]}>
                  <Text style={[ef.scoreNum, { color: scoreColor }]}>{sc.toFixed(0)}</Text>
                  <Text style={[ef.scoreMax, { color: colors.mutedForeground }]}>/100</Text>
                </View>
                <View style={{ flex: 1, gap: 4 }}>
                  <View style={[ef.barBg, { backgroundColor: colors.muted }]}>
                    <View style={[ef.barFill, { width: `${Math.max(2, sc)}%` as any, backgroundColor: scoreColor }]} />
                  </View>
                  <Text style={[ef.recTxt, { color: colors.foreground }]}>{rec}</Text>
                  {mom.trades > 0 && (
                    <Text style={[ef.smallTxt, { color: colors.mutedForeground }]}>
                      {momEmoji} Win Rate {mom.win_rate}% | {dirAr} | {mom.trades} صفقات
                    </Text>
                  )}
                </View>
              </View>

              {/* Factors */}
              {factors.length > 0 && (
                <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 5 }}>
                  {factors.map((f, i) => (
                    <View key={i} style={[ef.factorChip, { backgroundColor: colors.muted, borderColor: colors.border }]}>
                      <Text style={[ef.factorTxt, { color: colors.mutedForeground }]}>{f}</Text>
                    </View>
                  ))}
                </View>
              )}

              {/* Consolidate button */}
              <View style={{ flexDirection: "row", gap: 8, alignItems: "center", marginTop: 2 }}>
                <Pressable
                  style={[ef.consolidateBtn, { backgroundColor: colors.muted, borderColor: colors.border }]}
                  onPress={handleConsolidate}
                  disabled={consolidating}
                >
                  {consolidating
                    ? <ActivityIndicator size="small" color={colors.primary} />
                    : <><Feather name="database" size={13} color={colors.primary} /><Text style={[ef.consolidateTxt, { color: colors.primary }]}>دمج الذاكرة الآن</Text></>
                  }
                </Pressable>
                {!!consolidateMsg && (
                  <Text style={[ef.consolidateMsg, { color: colors.mutedForeground }]} numberOfLines={2}>{consolidateMsg}</Text>
                )}
              </View>
            </Card>
          </>
        );
      })()}

      {/* ── State Summary ── */}
      <SectionHeader title="حالة الأيجنت" icon="cpu" color="#3B82F6" />
      <Card>
        <View style={s.stateRow}>
          {/* Strategy */}
          <View style={[s.stateBox, { backgroundColor: `${curStrategy.color}14`, borderColor: `${curStrategy.color}30` }]}>
            <Feather name={curStrategy.icon as any} size={16} color={curStrategy.color} />
            <Text style={[s.stateLabel, { color: colors.mutedForeground }]}>الاستراتيجية</Text>
            <Text style={[s.stateValue, { color: curStrategy.color }]}>{curStrategy.label}</Text>
            <Text style={[s.stateConf, { color: colors.mutedForeground }]}>
              ثقة {((st?.confidence ?? 1) * 100).toFixed(0)}%
            </Text>
          </View>

          {/* Streak */}
          <View style={[s.stateBox, {
            backgroundColor: (sk?.consecutive_losses ?? 0) > 0 ? "#EF444414" : "#10B98114",
            borderColor:     (sk?.consecutive_losses ?? 0) > 0 ? "#EF444430" : "#10B98130",
          }]}>
            <Feather
              name={(sk?.consecutive_losses ?? 0) > 0 ? "trending-down" : "trending-up"}
              size={16}
              color={(sk?.consecutive_losses ?? 0) > 0 ? "#EF4444" : "#10B981"}
            />
            <Text style={[s.stateLabel, { color: colors.mutedForeground }]}>السلسلة</Text>
            <Text style={[s.stateValue, { color: (sk?.consecutive_losses ?? 0) > 0 ? "#EF4444" : "#10B981" }]}>
              {(sk?.consecutive_losses ?? 0) > 0
                ? `🔴 ×${sk?.consecutive_losses}`
                : `🟢 ×${sk?.consecutive_wins}`}
            </Text>
            <View style={{ flexDirection: "row", gap: 3, marginTop: 2 }}>
              {(sk?.last_results ?? []).slice(-8).map((r, i) => <ResultDot key={i} win={r} />)}
            </View>
          </View>

          {/* Target */}
          <View style={[s.stateBox, { backgroundColor: `${colors.primary}14`, borderColor: `${colors.primary}30` }]}>
            <Feather name="target" size={16} color={colors.primary} />
            <Text style={[s.stateLabel, { color: colors.mutedForeground }]}>الهدف</Text>
            <Text style={[s.stateValue, { color: colors.primary }]}>{cfg?.target_win_rate?.toFixed(0)}%</Text>
            <Text style={[s.stateConf, { color: colors.mutedForeground }]}>
              حد {cfg?.current_threshold}%
            </Text>
          </View>
        </View>

        {/* Last results row */}
        {(sk?.last_results?.length ?? 0) > 0 && (
          <View style={{ flexDirection: "row", gap: 4, marginTop: 10, alignItems: "center" }}>
            <Text style={[s.smallLabel, { color: colors.mutedForeground }]}>آخر نتائج:</Text>
            {(sk?.last_results ?? []).slice(-10).map((r, i) => (
              <View key={i} style={[s.resultChip, { backgroundColor: r ? "#10B98122" : "#EF444422", borderColor: r ? "#10B98155" : "#EF444455" }]}>
                <Text style={{ fontSize: 9, color: r ? "#10B981" : "#EF4444", fontWeight: "700" }}>{r ? "W" : "L"}</Text>
              </View>
            ))}
          </View>
        )}
      </Card>

      {/* ── Goal ── */}
      <SectionHeader title="هدف الأيجنت" icon="flag" color="#10B981" />
      <Card>
        {editGoal ? (
          <View style={{ gap: 8 }}>
            <TextInput
              style={[s.goalInput, { color: colors.foreground, borderColor: colors.primary, backgroundColor: colors.muted }]}
              value={goalInput}
              onChangeText={setGoalInput}
              placeholder="أدخل هدفاً جديداً للأيجنت..."
              placeholderTextColor={colors.mutedForeground}
              multiline
            />
            <View style={{ flexDirection: "row", gap: 8 }}>
              <Pressable
                style={[s.goalBtn, { backgroundColor: colors.primary, flex: 1 }]}
                onPress={async () => {
                  await sendCommand("set_goal", goalInput);
                  setEditGoal(false);
                }}
              >
                <Text style={s.goalBtnTxt}>حفظ</Text>
              </Pressable>
              <Pressable style={[s.goalBtn, { backgroundColor: colors.muted, borderWidth: 1, borderColor: colors.border }]} onPress={() => setEditGoal(false)}>
                <Text style={[s.goalBtnTxt, { color: colors.mutedForeground }]}>إلغاء</Text>
              </Pressable>
            </View>
          </View>
        ) : (
          <Pressable onPress={() => setEditGoal(true)} style={{ flexDirection: "row", alignItems: "flex-start", gap: 10 }}>
            <Feather name="flag" size={14} color={colors.primary} style={{ marginTop: 2 }} />
            <Text style={[s.goalText, { color: colors.foreground, flex: 1 }]}>{st?.goal || "لم يُحدَّد هدف"}</Text>
            <Feather name="edit-2" size={13} color={colors.mutedForeground} />
          </Pressable>
        )}
      </Card>

      {/* ── Strategy Control ── */}
      <SectionHeader title="اختيار الاستراتيجية" icon="sliders" color="#F59E0B" />
      <Card style={{ gap: 8 }}>
        <View style={s.stratGrid}>
          {STRATEGIES.map(strat => {
            const active = strat.id === st?.current;
            return (
              <Pressable
                key={strat.id}
                onPress={() => sendCommand("set_strategy", strat.id)}
                disabled={!!cmdLoading}
                style={[s.stratBtn, {
                  backgroundColor: active ? `${strat.color}18` : colors.muted,
                  borderColor:     active ? strat.color : colors.border,
                  borderWidth:     active ? 2 : 1,
                }]}
              >
                {isLoading("set_strategy" + strat.id) ? (
                  <ActivityIndicator size="small" color={strat.color} />
                ) : (
                  <Feather name={strat.icon as any} size={14} color={active ? strat.color : colors.mutedForeground} />
                )}
                <Text style={[s.stratLabel, { color: active ? strat.color : colors.foreground, fontWeight: active ? "700" : "500" }]}>
                  {strat.label}
                </Text>
                {active && <View style={[s.activeDot, { backgroundColor: strat.color }]} />}
              </Pressable>
            );
          })}
        </View>
        <Text style={[s.stratDesc, { color: colors.mutedForeground }]}>
          {curStrategy.desc}
        </Text>
        {msgMap["set_strategy"] && (
          <Text style={[s.msg, { color: msgMap["set_strategy"].startsWith("✅") ? colors.primary : "#EF4444" }]}>
            {msgMap["set_strategy"]}
          </Text>
        )}
      </Card>

      {/* ── Threshold Controls ── */}
      <SectionHeader title="معاملات الأيجنت" icon="sliders" color="#8B5CF6" />
      <Card style={{ gap: 10 }}>
        {/* Confidence Threshold */}
        <View>
          <View style={s.paramRow}>
            <Text style={[s.paramLabel, { color: colors.foreground }]}>حد الثقة (Confidence)</Text>
            <Text style={[s.paramValue, { color: colors.primary }]}>{cfg?.current_threshold}%</Text>
          </View>
          <View style={s.thresholdBtns}>
            {[40, 50, 55, 60, 65, 70, 75, 80].map(v => {
              const active = v === cfg?.current_threshold;
              return (
                <Pressable
                  key={v}
                  onPress={() => sendCommand("set_threshold", undefined, v)}
                  disabled={!!cmdLoading}
                  style={[s.tBtn, {
                    backgroundColor: active ? colors.primary : colors.muted,
                    borderColor:     active ? colors.primary : colors.border,
                  }]}
                >
                  <Text style={[s.tBtnTxt, { color: active ? "#fff" : colors.mutedForeground }]}>{v}</Text>
                </Pressable>
              );
            })}
          </View>
          {msgMap["set_threshold"] && (
            <Text style={[s.msg, { color: msgMap["set_threshold"].startsWith("✅") ? colors.primary : "#EF4444" }]}>
              {msgMap["set_threshold"]}
            </Text>
          )}
        </View>

        <View style={[s.divider, { backgroundColor: colors.border }]} />

        {/* Target Win Rate */}
        <View>
          <View style={s.paramRow}>
            <Text style={[s.paramLabel, { color: colors.foreground }]}>هدف الفوز (Win Rate)</Text>
            <Text style={[s.paramValue, { color: "#10B981" }]}>{cfg?.target_win_rate?.toFixed(0)}%</Text>
          </View>
          <View style={s.thresholdBtns}>
            {[55, 60, 65, 70, 75, 80].map(v => {
              const active = v === (cfg?.target_win_rate ?? 65);
              return (
                <Pressable
                  key={v}
                  onPress={() => sendCommand("set_win_rate", undefined, v)}
                  disabled={!!cmdLoading}
                  style={[s.tBtn, {
                    backgroundColor: active ? "#10B981" : colors.muted,
                    borderColor:     active ? "#10B981" : colors.border,
                  }]}
                >
                  <Text style={[s.tBtnTxt, { color: active ? "#fff" : colors.mutedForeground }]}>{v}</Text>
                </Pressable>
              );
            })}
          </View>
          {msgMap["set_win_rate"] && (
            <Text style={[s.msg, { color: msgMap["set_win_rate"].startsWith("✅") ? "#10B981" : "#EF4444" }]}>
              {msgMap["set_win_rate"]}
            </Text>
          )}
        </View>
      </Card>

      {/* ── Quick Actions ── */}
      <SectionHeader title="إجراءات سريعة" icon="zap" color="#EF4444" />
      <Card style={{ gap: 8 }}>
        <View style={s.actionRow}>
          <Pressable
            style={[s.actionBtn, { backgroundColor: "#EF444418", borderColor: "#EF444444" }]}
            onPress={() => Alert.alert(
              "إيقاف طارئ",
              "سيتوقف الأيجنت فوراً ويحتاج إعادة تشغيل يدوية. هل أنت متأكد؟",
              [
                { text: "إلغاء", style: "cancel" },
                { text: "إيقاف", style: "destructive", onPress: () => sendCommand("halt") },
              ]
            )}
            disabled={!!cmdLoading || halted}
          >
            {isLoading("halt") ? <ActivityIndicator size="small" color="#EF4444" /> : <Feather name="alert-octagon" size={14} color="#EF4444" />}
            <Text style={[s.actionBtnTxt, { color: "#EF4444" }]}>إيقاف طارئ</Text>
          </Pressable>

          <Pressable
            style={[s.actionBtn, { backgroundColor: "#10B98118", borderColor: "#10B98144" }]}
            onPress={() => sendCommand("resume")}
            disabled={!!cmdLoading || !halted}
          >
            {isLoading("resume") ? <ActivityIndicator size="small" color="#10B981" /> : <Feather name="play" size={14} color="#10B981" />}
            <Text style={[s.actionBtnTxt, { color: "#10B981" }]}>استئناف</Text>
          </Pressable>
        </View>

        <View style={s.actionRow}>
          <Pressable
            style={[s.actionBtn, { backgroundColor: `${colors.primary}14`, borderColor: `${colors.primary}44`, flex: 1 }]}
            onPress={() => {
              Alert.alert("إعادة ضبط الأنماط", "سيتم مسح نقاط الأنماط وبدء التعلم من جديد.", [
                { text: "إلغاء", style: "cancel" },
                { text: "إعادة ضبط", onPress: () => sendCommand("reset_patterns") },
              ]);
            }}
            disabled={!!cmdLoading}
          >
            <Feather name="rotate-ccw" size={14} color={colors.primary} />
            <Text style={[s.actionBtnTxt, { color: colors.primary }]}>إعادة ضبط الأنماط</Text>
          </Pressable>
        </View>

        {msgMap["halt"]   && <Text style={[s.msg, { color: "#EF4444" }]}>{msgMap["halt"]}</Text>}
        {msgMap["resume"] && <Text style={[s.msg, { color: "#10B981" }]}>{msgMap["resume"]}</Text>}
        {msgMap["reset_patterns"] && <Text style={[s.msg, { color: colors.primary }]}>{msgMap["reset_patterns"]}</Text>}
      </Card>

      {/* ── AI Providers Health ── */}
      <SectionHeader title="صحة مزودي الذكاء الاصطناعي" icon="cpu" color="#4285F4" />
      <Card style={{ gap: 6 }}>
        {(!ai?.keys || ai.keys.length === 0) ? (
          <View style={s.emptyBox}>
            <Feather name="cpu" size={24} color={colors.mutedForeground} />
            <Text style={[s.emptyTxt, { color: colors.mutedForeground }]}>لا يوجد مزود AI مضاف</Text>
            <Text style={[s.emptySub, { color: colors.mutedForeground }]}>أضف مفاتيح API من صفحة CONFIG</Text>
          </View>
        ) : (
          ai.keys.map((k, i) => {
            const color = PROVIDER_COLORS[k.provider] ?? "#6B7280";
            const successRate = k.total_calls > 0 ? Math.round(k.success_calls / k.total_calls * 100) : 0;
            return (
              <View key={i} style={[s.aiKeyRow, { borderColor: k.available ? `${color}44` : colors.border, backgroundColor: k.available ? `${color}08` : colors.muted }]}>
                <View style={[s.aiDot, { backgroundColor: k.available ? color : colors.mutedForeground }]} />
                <View style={{ flex: 1 }}>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                    <Text style={[s.aiKeyLabel, { color: colors.foreground }]}>{k.label}</Text>
                    <View style={[s.aiProvBadge, { backgroundColor: `${color}20` }]}>
                      <Text style={[s.aiProvBadgeTxt, { color }]}>{k.provider}</Text>
                    </View>
                  </View>
                  <Text style={[s.aiKeyModel, { color: colors.mutedForeground }]} numberOfLines={1}>{k.model_name}</Text>
                  <View style={s.aiStats}>
                    <Text style={[s.aiStat, { color: colors.mutedForeground }]}>📊 {k.total_calls} استدعاء</Text>
                    {k.total_calls > 0 && <Text style={[s.aiStat, { color: successRate > 80 ? "#10B981" : "#F59E0B" }]}>✅ {successRate}%</Text>}
                    {k.failed_calls > 0 && <Text style={[s.aiStat, { color: "#EF4444" }]}>❌ {k.failed_calls}</Text>}
                  </View>
                </View>
                <View style={{ alignItems: "flex-end", gap: 4 }}>
                  <View style={[s.availBadge, { backgroundColor: k.available ? "#10B98122" : "#EF444422" }]}>
                    <Text style={[s.availBadgeTxt, { color: k.available ? "#10B981" : "#EF4444" }]}>
                      {k.available ? "نشط" : k.hours_remaining > 0 ? `${k.hours_remaining.toFixed(1)}h` : "محدود"}
                    </Text>
                  </View>
                </View>
              </View>
            );
          })
        )}
        <View style={[s.aiSummary, { borderColor: colors.border }]}>
          <Text style={[s.aiSummaryTxt, { color: colors.mutedForeground }]}>
            {ai?.available_keys ?? 0}/{ai?.total_keys ?? 0} مزود نشط
            {(ai?.available_keys ?? 0) === 0 && " — الأيجنت يعمل بقواعد بديلة"}
          </Text>
        </View>
      </Card>

      {/* ── Pattern Scores ── */}
      {(data?.patterns?.length ?? 0) > 0 && (
        <>
          <SectionHeader title="أداء الأنماط المتعلَّمة" icon="bar-chart-2" color="#F59E0B" />
          <Card style={{ gap: 6 }}>
            {data!.patterns.map((p, i) => {
              const wr = Math.round(p.win_rate);
              const color = wr >= 65 ? "#10B981" : wr >= 50 ? "#F59E0B" : "#EF4444";
              return (
                <View key={i} style={s.patternRow}>
                  <Text style={[s.patternName, { color: colors.foreground }]} numberOfLines={1}>{p.pattern}</Text>
                  <View style={s.patternBarWrap}>
                    <View style={[s.patternBar, { width: `${wr}%`, backgroundColor: color }]} />
                  </View>
                  <Text style={[s.patternWr, { color }]}>{wr}%</Text>
                  <Text style={[s.patternTotal, { color: colors.mutedForeground }]}>/{p.total}</Text>
                </View>
              );
            })}
          </Card>
        </>
      )}

      {/* ── Recent Lessons ── */}
      <SectionHeader title="الدروس المستفادة" icon="book-open" color="#10B981" />
      {(!data?.lessons || data.lessons.length === 0) ? (
        <Card>
          <View style={s.emptyBox}>
            <Feather name="book-open" size={24} color={colors.mutedForeground} />
            <Text style={[s.emptyTxt, { color: colors.mutedForeground }]}>لا توجد دروس بعد</Text>
            <Text style={[s.emptySub, { color: colors.mutedForeground }]}>ستُحفظ الدروس تلقائياً بعد كل صفقة</Text>
          </View>
        </Card>
      ) : (
        <View style={{ gap: 6, marginHorizontal: 16 }}>
          {data!.lessons.slice(0, 12).map((l, i) => {
            const win = l.outcome === "win";
            const isStrategic = l.lesson?.startsWith("[STRATEGIC INSIGHT]");
            return (
              <View key={i} style={[s.lessonRow, {
                borderColor: isStrategic ? "#8B5CF644" : (win ? "#10B98133" : "#EF444433"),
                backgroundColor: isStrategic ? "#8B5CF608" : (win ? "#10B98108" : "#EF444408"),
              }]}>
                <Text style={s.lessonIcon}>{isStrategic ? "💡" : win ? "✅" : "📌"}</Text>
                <View style={{ flex: 1 }}>
                  <Text style={[s.lessonTxt, { color: colors.foreground }]} numberOfLines={3}>
                    {l.lesson?.replace("[STRATEGIC INSIGHT] ", "") ?? "—"}
                  </Text>
                  <View style={s.lessonMeta}>
                    {l.symbol && l.symbol !== "PORTFOLIO" && (
                      <Text style={[s.lessonMetaTxt, { color: colors.primary }]}>{l.symbol}</Text>
                    )}
                    <Text style={[s.lessonMetaTxt, { color: colors.mutedForeground }]}>
                      {l.created_at ? new Date(l.created_at).toLocaleDateString("ar-DZ") : ""}
                    </Text>
                  </View>
                </View>
              </View>
            );
          })}
        </View>
      )}

      {/* ══════════════════════════════════════════════════════════════════ */}
      {/* ── MEMORY & KNOWLEDGE ─ نظام الذاكرة الشاملة ─────────────────── */}
      {/* ══════════════════════════════════════════════════════════════════ */}
      <SectionHeader title="ذاكرة البوت الشاملة" icon="database" color="#8B5CF6" />

      {/* Stats row */}
      {memData?.stats && (
        <View style={{ flexDirection: "row", gap: 8, marginHorizontal: 16, marginBottom: 4 }}>
          {[
            { label: "دروس", value: memData.stats.total_lessons, color: "#8B5CF6", icon: "book-open" },
            { label: "ربح", value: memData.stats.wins, color: "#10B981", icon: "trending-up" },
            { label: "خسارة", value: memData.stats.losses, color: "#EF4444", icon: "trending-down" },
            { label: "معرفة", value: memData.stats.total_knowledge, color: "#F59E0B", icon: "cpu" },
          ].map(st => (
            <View key={st.label} style={[ms.statCard, { borderColor: `${st.color}33`, backgroundColor: `${st.color}0D`, flex: 1 }]}>
              <Feather name={st.icon as any} size={12} color={st.color} />
              <Text style={[ms.statNum, { color: st.color }]}>{st.value ?? 0}</Text>
              <Text style={[ms.statLabel, { color: colors.mutedForeground }]}>{st.label}</Text>
            </View>
          ))}
        </View>
      )}

      {/* Search bar */}
      <View style={[ms.searchRow, { backgroundColor: colors.card, borderColor: colors.border, marginHorizontal: 16 }]}>
        <Feather name="search" size={14} color={colors.mutedForeground} />
        <TextInput
          value={memSearch}
          onChangeText={handleMemSearch}
          placeholder="ابحث في الذاكرة... (عملة، نمط، حدث)"
          placeholderTextColor={colors.mutedForeground}
          style={[ms.searchInput, { color: colors.foreground }]}
        />
        {memSearching && <ActivityIndicator size="small" color={colors.mutedForeground} />}
        {memSearch.length > 0 && !memSearching && (
          <Pressable onPress={() => { setMemSearch(""); setMemSearchResults(null); }}>
            <Feather name="x" size={14} color={colors.mutedForeground} />
          </Pressable>
        )}
      </View>

      {/* Tabs: Lessons / Knowledge */}
      <View style={[ms.tabRow, { marginHorizontal: 16 }]}>
        {(["lessons", "knowledge"] as const).map(t => (
          <Pressable
            key={t}
            onPress={() => { setMemTab(t); Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light); }}
            style={[ms.tabBtn, {
              backgroundColor: memTab === t ? "#8B5CF620" : colors.muted,
              borderColor:     memTab === t ? "#8B5CF6" : colors.border,
              borderWidth:     memTab === t ? 2 : 1,
              flex: 1,
            }]}
          >
            <Feather name={t === "lessons" ? "book-open" : "cpu"} size={12} color={memTab === t ? "#8B5CF6" : colors.mutedForeground} />
            <Text style={[ms.tabBtnTxt, { color: memTab === t ? "#8B5CF6" : colors.mutedForeground, fontWeight: memTab === t ? "800" : "500" }]}>
              {t === "lessons" ? `دروس (${(memSearchResults ?? memData)?.lessons?.length ?? memData?.stats?.total_lessons ?? 0})` : `معرفة (${(memSearchResults ?? memData)?.knowledge?.length ?? memData?.stats?.total_knowledge ?? 0})`}
            </Text>
          </Pressable>
        ))}
      </View>

      {/* ── Lessons List ── */}
      {memTab === "lessons" && (
        <View style={{ gap: 5, marginHorizontal: 16 }}>
          {((memSearchResults?.lessons ?? memData?.recent_lessons) ?? []).slice(0, 40).map((l: any, i: number) => {
            const win = l.outcome === "win";
            const isUser = l.category === "user";
            const imp = parseFloat(l.importance ?? 5);
            const color = isUser ? "#F59E0B" : win ? "#10B981" : l.outcome === "open" ? "#6366F1" : "#EF4444";
            const icon  = isUser ? "🔔" : win ? "✅" : l.outcome === "open" ? "🔄" : l.outcome === "instruction" ? "📋" : "📌";
            return (
              <View key={l.id ?? i} style={[ms.lessonCard, { borderColor: `${color}33`, backgroundColor: `${color}08` }]}>
                <Text style={ms.lessonIcon}>{icon}</Text>
                <View style={{ flex: 1 }}>
                  <Text style={[ms.lessonText, { color: colors.foreground }]} numberOfLines={4}>
                    {l.lesson ?? "—"}
                  </Text>
                  <View style={ms.lessonFooter}>
                    {l.symbol ? <Text style={[ms.lessonTag, { color, borderColor: `${color}44` }]}>{l.symbol}</Text> : null}
                    {l.pattern ? <Text style={[ms.lessonTag, { color: colors.mutedForeground, borderColor: colors.border }]}>{l.pattern}</Text> : null}
                    <Text style={[ms.lessonDate, { color: colors.mutedForeground }]}>
                      {imp.toFixed(0)}/10 • {l.created_at ? new Date(l.created_at).toLocaleDateString("ar-SA") : ""}
                    </Text>
                  </View>
                </View>
                <Pressable onPress={() => l.id && handleDeleteLesson(l.id)} hitSlop={8} style={{ padding: 4, marginTop: 2 }}>
                  <Feather name="trash-2" size={12} color={`${colors.destructive}88`} />
                </Pressable>
              </View>
            );
          })}
          {((memSearchResults?.lessons ?? memData?.recent_lessons) ?? []).length === 0 && (
            <View style={ms.emptyMem}>
              <Feather name="book-open" size={28} color={colors.mutedForeground} />
              <Text style={[ms.emptyMemTxt, { color: colors.mutedForeground }]}>لا توجد دروس بعد</Text>
            </View>
          )}
        </View>
      )}

      {/* ── Knowledge List ── */}
      {memTab === "knowledge" && (
        <View style={{ gap: 5, marginHorizontal: 16 }}>
          {/* Add note button */}
          <Pressable
            onPress={() => { setShowAddNote(!showAddNote); Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light); }}
            style={[ms.addNoteBtn, { borderColor: "#8B5CF666", backgroundColor: "#8B5CF60D" }]}
          >
            <Feather name={showAddNote ? "chevron-up" : "plus"} size={14} color="#8B5CF6" />
            <Text style={[ms.addNoteTxt, { color: "#8B5CF6" }]}>
              {showAddNote ? "إلغاء" : "إضافة معرفة يدوية"}
            </Text>
          </Pressable>

          {/* Add note form */}
          {showAddNote && (
            <View style={[ms.addNoteForm, { backgroundColor: colors.card, borderColor: "#8B5CF644" }]}>
              <TextInput
                value={noteTitle}
                onChangeText={setNoteTitle}
                placeholder="العنوان (مثل: قاعدة BTC، تعليمة مهمة...)"
                placeholderTextColor={colors.mutedForeground}
                style={[ms.noteInput, { color: colors.foreground, borderColor: colors.border }]}
              />
              <TextInput
                value={noteContent}
                onChangeText={setNoteContent}
                placeholder="المحتوى — هذا سيصبح جزءاً من ذاكرة البوت الدائمة"
                placeholderTextColor={colors.mutedForeground}
                multiline
                numberOfLines={3}
                style={[ms.noteInput, ms.noteInputMulti, { color: colors.foreground, borderColor: colors.border }]}
              />
              {/* Category selector */}
              <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6 }}>
                {[
                  { id: "general", label: "عام", color: "#6B7280" },
                  { id: "strategy", label: "استراتيجية", color: "#8B5CF6" },
                  { id: "risk", label: "مخاطرة", color: "#EF4444" },
                  { id: "user", label: "تعليمة", color: "#F59E0B" },
                  { id: "market", label: "سوق", color: "#10B981" },
                ].map(c => (
                  <Pressable
                    key={c.id}
                    onPress={() => setNoteCategory(c.id)}
                    style={[ms.catBtn, {
                      backgroundColor: noteCategory === c.id ? `${c.color}20` : colors.muted,
                      borderColor: noteCategory === c.id ? c.color : colors.border,
                    }]}
                  >
                    <Text style={[ms.catBtnTxt, { color: noteCategory === c.id ? c.color : colors.mutedForeground }]}>{c.label}</Text>
                  </Pressable>
                ))}
              </View>
              <Pressable
                onPress={handleAddNote}
                disabled={noteSaving || !noteTitle.trim() || !noteContent.trim()}
                style={[ms.saveNoteBtn, { backgroundColor: "#8B5CF6", opacity: noteSaving ? 0.6 : 1 }]}
              >
                {noteSaving ? (
                  <ActivityIndicator size="small" color="#fff" />
                ) : (
                  <>
                    <Feather name="save" size={13} color="#fff" />
                    <Text style={ms.saveNoteTxt}>حفظ في الذاكرة الدائمة</Text>
                  </>
                )}
              </Pressable>
            </View>
          )}

          {/* Knowledge items */}
          {((memSearchResults?.knowledge ?? memData?.knowledge) ?? []).slice(0, 40).map((k: any, i: number) => {
            const CAT_COLORS: Record<string,string> = {
              strategy: "#8B5CF6", risk: "#EF4444", user: "#F59E0B",
              market: "#10B981", general: "#6B7280", ai: "#4285F4",
            };
            const color = CAT_COLORS[k.category] ?? "#6B7280";
            const imp = parseFloat(k.importance ?? 5);
            return (
              <View key={k.id ?? i} style={[ms.knowCard, { borderColor: `${color}33`, backgroundColor: `${color}08` }]}>
                <View style={{ flex: 1 }}>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                    <View style={[ms.catDot, { backgroundColor: color }]} />
                    <Text style={[ms.knowTitle, { color: colors.foreground }]} numberOfLines={1}>{k.title}</Text>
                    <View style={[ms.catBadge, { backgroundColor: `${color}20` }]}>
                      <Text style={[ms.catBadgeTxt, { color }]}>{k.category}</Text>
                    </View>
                    <Text style={[ms.knowImp, { color: colors.mutedForeground }]}>{imp.toFixed(0)}/10</Text>
                  </View>
                  <Text style={[ms.knowContent, { color: colors.foreground }]} numberOfLines={3}>
                    {k.content}
                  </Text>
                  {k.source && (
                    <Text style={[ms.knowSource, { color: colors.mutedForeground }]}>
                      المصدر: {k.source} • {k.updated_at ? new Date(k.updated_at).toLocaleDateString("ar-SA") : ""}
                    </Text>
                  )}
                </View>
                <Pressable onPress={() => k.id && handleDeleteKnowledge(k.id)} hitSlop={8} style={{ padding: 4, marginTop: 2 }}>
                  <Feather name="trash-2" size={12} color={`${colors.destructive}88`} />
                </Pressable>
              </View>
            );
          })}
          {((memSearchResults?.knowledge ?? memData?.knowledge) ?? []).length === 0 && !showAddNote && (
            <View style={ms.emptyMem}>
              <Feather name="cpu" size={28} color={colors.mutedForeground} />
              <Text style={[ms.emptyMemTxt, { color: colors.mutedForeground }]}>لا توجد معرفة مخزّنة</Text>
              <Text style={[ms.emptyMemSub, { color: colors.mutedForeground }]}>أضف معرفة يدوية أو دع البوت يتعلم تلقائياً</Text>
            </View>
          )}
        </View>
      )}

      {/* ══════════════════════════════════════════════════════════════════ */}
      {/* ── Internal Thoughts Feed ── */}
      {(data?.recent_thoughts?.length ?? 0) > 0 && (
        <>
          <SectionHeader title="سجل أفكار الجلسة" icon="terminal" color="#6366F1" />
          <Card style={{ gap: 4 }}>
            {data!.recent_thoughts.slice().reverse().slice(0, 8).map((t, i) => (
              <View key={i} style={[s.thoughtRow, { borderLeftColor: "#6366F1", backgroundColor: colors.muted }]}>
                <Text style={[s.thoughtTxt, { color: colors.foreground }]}>{t}</Text>
              </View>
            ))}
          </Card>
        </>
      )}

      {/* ── BRAIN CHAT — Natural Language Interface ── */}
      <SectionHeader title="تحدث مع العقل — اطلب أي شيء" icon="message-square" color="#6366F1" />

      {/* Quick skill shortcuts */}
      <View style={{ paddingHorizontal: 16, marginBottom: 8 }}>
        <Text style={[{ fontSize: 10, fontWeight: "600", letterSpacing: 0.8, color: colors.mutedForeground, marginBottom: 6 }]}>
          اضغط للسؤال السريع:
        </Text>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6 }}>
          {QUICK_SKILLS.map((sk, i) => (
            <Pressable
              key={i}
              style={[qs.btn, { backgroundColor: colors.muted, borderColor: colors.border }]}
              onPress={() => sendBrainMessage(sk.msg)}
              disabled={chatLoading}
            >
              <Text style={[qs.txt, { color: colors.foreground }]}>{sk.label}</Text>
            </Pressable>
          ))}
        </View>
      </View>
    </ScrollView>

    {/* Brain Chat — fixed at bottom (sibling of ScrollView inside root KAV) */}
      <View style={[s.chatContainer, { borderColor: colors.border, backgroundColor: colors.background, borderTopWidth: 1 }]}>
        <FlatList
          ref={chatListRef}
          data={chatMessages}
          inverted
          keyExtractor={m => m.id}
          keyboardDismissMode="interactive"
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
          style={{ maxHeight: 260 }}
          contentContainerStyle={{ paddingHorizontal: 12, paddingTop: 8, gap: 6 }}
          ListHeaderComponent={chatLoading ? (
            <View style={[s.chatBubble, s.chatBotBubble, { backgroundColor: colors.card, borderColor: colors.border }]}>
              <ActivityIndicator size="small" color="#6366F1" />
              <Text style={[s.chatTyping, { color: colors.mutedForeground }]}>العقل يفكر...</Text>
            </View>
          ) : null}
          renderItem={({ item }) => {
            const isUser = item.role === "user";
            const isTradeAuto = item.metadata?.type === "trade_auto";
            const tradeEvent  = item.metadata?.event ?? "";
            const provColor   = item.provider ? (PROVIDER_COLORS[item.provider] ?? "#6366F1") : "#6366F1";

            // ── Trade auto-commentary card ─────────────────────────────────
            if (isTradeAuto) {
              const tradeAccent =
                tradeEvent === "open"       ? "#6366F1" :
                tradeEvent === "close_win"  ? "#10B981" : "#EF4444";
              const tradeIcon =
                tradeEvent === "open"       ? "trending-up" :
                tradeEvent === "close_win"  ? "check-circle" : "alert-circle";
              const tradeLabel =
                tradeEvent === "open"       ? "تحليل دخول" :
                tradeEvent === "close_win"  ? "تقرير ربح"  : "تحليل خسارة";
              const sym = (item.metadata?.symbol ?? "").replace("/USDT", "");
              const pnl = item.metadata?.pnl;

              return (
                <View style={{ marginHorizontal: 10, marginVertical: 5 }}>
                  <View style={{
                    borderRadius: 14,
                    borderLeftWidth: 3,
                    borderLeftColor: tradeAccent,
                    backgroundColor: `${tradeAccent}11`,
                    padding: 12,
                    gap: 6,
                  }}>
                    {/* Header row */}
                    <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                      <View style={{
                        width: 22, height: 22, borderRadius: 11,
                        backgroundColor: `${tradeAccent}22`,
                        alignItems: "center", justifyContent: "center",
                      }}>
                        <Feather name={tradeIcon as any} size={11} color={tradeAccent} />
                      </View>
                      <Text style={{ fontSize: 11, fontWeight: "700", color: tradeAccent }}>
                        {tradeLabel}{sym ? ` — ${sym}` : ""}
                      </Text>
                      {pnl != null && (
                        <Text style={{
                          fontSize: 10, fontWeight: "700",
                          color: pnl >= 0 ? "#10B981" : "#EF4444",
                          marginLeft: "auto",
                        }}>
                          {pnl >= 0 ? "+" : ""}{pnl.toFixed(4)} USDT
                        </Text>
                      )}
                    </View>
                    {/* Content — skip header line (first line already shown) */}
                    <Text style={{ fontSize: 12, color: colors.foreground, lineHeight: 18 }}>
                      {item.content.replace(/^[^\n]+\n\n/, "")}
                    </Text>
                    {/* Footer */}
                    <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
                      <Feather name="clock" size={8} color={colors.mutedForeground} />
                      <Text style={{ fontSize: 9, color: colors.mutedForeground }}>
                        {new Date(item.timestamp).toLocaleTimeString("ar-SA", { hour: "2-digit", minute: "2-digit" })}
                      </Text>
                      <View style={{ width: 3, height: 3, borderRadius: 2, backgroundColor: tradeAccent, marginLeft: "auto" }} />
                      <Text style={{ fontSize: 9, color: tradeAccent, fontWeight: "700" }}>تلقائي</Text>
                    </View>
                  </View>
                </View>
              );
            }

            // ── Normal chat bubble ─────────────────────────────────────────
            // Split main reply from skill result block (separated by ---)
            const parts        = item.content.split(/\n---\n/);
            const mainContent  = parts[0]?.trim() ?? item.content;
            const skillContent = parts.slice(1).join("\n---\n").trim();

            return (
              <View style={[s.chatMsgWrap, isUser ? s.chatUserWrap : s.chatBotWrap]}>
                {!isUser && (
                  <View style={[s.chatAvatar, { backgroundColor: `${provColor}22` }]}>
                    <Feather name="cpu" size={9} color={provColor} />
                  </View>
                )}
                <View style={{ maxWidth: "85%", gap: 4 }}>
                  {/* Main reply bubble */}
                  {mainContent ? (
                    <View style={[
                      s.chatBubble,
                      isUser
                        ? [s.chatUserBubble, { backgroundColor: "#6366F1" }]
                        : [s.chatBotBubble, { backgroundColor: colors.card, borderColor: colors.border }],
                    ]}>
                      <Text style={[s.chatBubbleTxt, { color: isUser ? "#fff" : colors.foreground }]}>
                        {mainContent}
                      </Text>
                    </View>
                  ) : null}

                  {/* Skill result card — special styled block */}
                  {!isUser && skillContent ? (
                    <View style={{
                      borderRadius: 10,
                      borderLeftWidth: 3,
                      borderLeftColor: "#6366F1",
                      backgroundColor: `${provColor}0D`,
                      borderWidth: 1,
                      borderColor: `${provColor}22`,
                      padding: 10,
                    }}>
                      <View style={{ flexDirection: "row", alignItems: "center", gap: 5, marginBottom: 5 }}>
                        <Feather name="zap" size={10} color="#6366F1" />
                        <Text style={{ fontSize: 9, fontWeight: "800", color: "#6366F1", letterSpacing: 0.8, textTransform: "uppercase" }}>
                          نتيجة المهارة
                        </Text>
                      </View>
                      <Text style={{ fontSize: 12, color: colors.foreground, lineHeight: 18, fontFamily: "monospace" }}>
                        {skillContent}
                      </Text>
                    </View>
                  ) : null}

                  {/* If isUser and has ---, just show everything normally */}
                  {isUser && !mainContent ? (
                    <View style={[s.chatBubble, s.chatUserBubble, { backgroundColor: "#6366F1" }]}>
                      <Text style={[s.chatBubbleTxt, { color: "#fff" }]}>{item.content}</Text>
                    </View>
                  ) : null}

                  {item.executed_command ? (
                    <View style={s.cmdBadge}>
                      <Feather name="check-circle" size={9} color="#10B981" />
                      <Text style={s.cmdBadgeTxt}>✅ نُفِّذ: {item.executed_command}</Text>
                    </View>
                  ) : null}

                  {!isUser && item.provider && item.provider !== "rule-based" ? (
                    <View style={{ flexDirection: "row", alignItems: "center", gap: 3, marginLeft: 4 }}>
                      <View style={{ width: 4, height: 4, borderRadius: 2, backgroundColor: provColor }} />
                      <Text style={{ fontSize: 9, color: provColor, fontWeight: "700" }}>{item.provider}</Text>
                    </View>
                  ) : null}
                </View>
              </View>
            );
          }}
        />

        {/* Quick command chips — Trading + Meta */}
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          style={{ paddingVertical: 6, borderTopWidth: 1, borderTopColor: colors.border }}
          contentContainerStyle={{ paddingHorizontal: 12, gap: 6 }}
        >
          {[
            { label: "📊 أداؤك الآن",          msg: "كيف أداؤك الآن؟ اعطني تقرير شامل" },
            { label: "⚡ غيّر Scalping",        msg: "غيّر الاستراتيجية إلى Scalping فوراً" },
            { label: "🛡️ ارفع حد الثقة 65%",   msg: "ارفع حد الثقة إلى 65%" },
            { label: "⏸️ أوقف البوت",           msg: "أوقف البوت الآن" },
            { label: "▶️ استأنف العمل",         msg: "استأنف العمل" },
            { label: "📂 اعرض ملفات الواجهة",   msg: "اعرض لي قائمة ملفات artifacts/mobile/app/(tabs)" },
            { label: "🗄️ آخر 5 صفقات DB",       msg: "نفّذ: SELECT symbol, side, status, pnl FROM trades ORDER BY created_at DESC LIMIT 5" },
            { label: "🔧 خريطة المشروع",         msg: "اعرض لي خريطة المشروع الكاملة" },
            { label: "🎨 عدّل لون التبويب",      msg: "اقرأ ملف artifacts/mobile/app/(tabs)/_layout.tsx ثم أخبرني بترتيب التبويبات الحالي" },
            { label: "🧠 ما تعلمته؟",            msg: "ما الدروس التي تعلمتها حتى الآن؟" },
          ].map(chip => (
            <Pressable
              key={chip.label}
              onPress={() => sendBrainMessage(chip.msg)}
              style={[s.chip, { backgroundColor: `#6366F118`, borderColor: `#6366F144` }]}
            >
              <Text style={[s.chipTxt, { color: "#6366F1" }]}>{chip.label}</Text>
            </Pressable>
          ))}
        </ScrollView>

        {/* Input row */}
        <View style={[s.chatInputRow, { borderTopColor: colors.border, paddingBottom: bottomPad + 6 }]}>
          <TextInput
            style={[s.chatInput, { backgroundColor: colors.card, color: colors.foreground, borderColor: colors.border }]}
            placeholder="أمر البوت بأي شيء — ملفات، SQL، واجهة، باك اند..."
            placeholderTextColor={colors.mutedForeground}
            value={chatInput}
            onChangeText={setChatInput}
            multiline
            returnKeyType="send"
            blurOnSubmit
            onSubmitEditing={() => sendBrainMessage()}
          />
          <Pressable
            onPress={() => sendBrainMessage()}
            disabled={!chatInput.trim() || chatLoading}
            style={[s.chatSendBtn, { backgroundColor: chatInput.trim() && !chatLoading ? "#6366F1" : colors.muted }]}
          >
            <Feather name="send" size={16} color={chatInput.trim() && !chatLoading ? "#fff" : colors.mutedForeground} />
          </Pressable>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const s = StyleSheet.create({
  center:        { flex: 1, alignItems: "center", justifyContent: "center", gap: 12 },
  loadTxt:       { fontSize: 13 },
  header:        { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: 16, paddingBottom: 8 },
  headerLeft:    { gap: 2 },
  headerTitle:   { fontSize: 20, fontWeight: "800", letterSpacing: 1 },
  headerSub:     { fontSize: 11 },
  refreshBtn:    { padding: 10, borderRadius: 10, borderWidth: 1 },

  haltBanner:    { flexDirection: "row", alignItems: "center", gap: 12, margin: 16, padding: 14, borderRadius: 12, backgroundColor: "#EF444418", borderWidth: 1.5, borderColor: "#EF4444" },
  haltTitle:     { fontSize: 13, fontWeight: "700", color: "#EF4444" },
  haltSub:       { fontSize: 11, color: "#EF4444", opacity: 0.8, marginTop: 2 },
  resumeBtn:     { backgroundColor: "#EF4444", paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8 },
  resumeBtnTxt:  { fontSize: 12, fontWeight: "700", color: "#fff" },

  stateRow:      { flexDirection: "row", gap: 8 },
  stateBox:      { flex: 1, padding: 12, borderRadius: 10, borderWidth: 1, alignItems: "center", gap: 4 },
  stateLabel:    { fontSize: 9, fontWeight: "600", letterSpacing: 0.5, textTransform: "uppercase", textAlign: "center" },
  stateValue:    { fontSize: 13, fontWeight: "800", textAlign: "center" },
  stateConf:     { fontSize: 9, textAlign: "center" },
  smallLabel:    { fontSize: 10 },
  resultChip:    { width: 18, height: 18, borderRadius: 4, alignItems: "center", justifyContent: "center", borderWidth: 1 },

  goalText:      { fontSize: 13, lineHeight: 20 },
  goalInput:     { fontSize: 13, borderRadius: 8, borderWidth: 1.5, padding: 10, lineHeight: 20, minHeight: 60 },
  goalBtn:       { paddingVertical: 10, borderRadius: 8, alignItems: "center" },
  goalBtnTxt:    { fontSize: 13, fontWeight: "700", color: "#fff" },

  stratGrid:     { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  stratBtn:      { flexDirection: "row", alignItems: "center", gap: 6, paddingVertical: 9, paddingHorizontal: 12, borderRadius: 10, minWidth: "48%", flex: 1 },
  stratLabel:    { fontSize: 12 },
  stratDesc:     { fontSize: 11, textAlign: "center", marginTop: 4 },
  activeDot:     { width: 6, height: 6, borderRadius: 3, marginLeft: "auto" },

  paramRow:      { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 8 },
  paramLabel:    { fontSize: 13, fontWeight: "600" },
  paramValue:    { fontSize: 16, fontWeight: "800" },
  thresholdBtns: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  tBtn:          { paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8, borderWidth: 1, alignItems: "center" },
  tBtnTxt:       { fontSize: 12, fontWeight: "600" },
  divider:       { height: 1, marginVertical: 4 },

  actionRow:     { flexDirection: "row", gap: 8 },
  actionBtn:     { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, paddingVertical: 12, borderRadius: 10, borderWidth: 1 },
  actionBtnTxt:  { fontSize: 13, fontWeight: "700" },

  aiKeyRow:      { flexDirection: "row", alignItems: "center", gap: 10, padding: 10, borderRadius: 10, borderWidth: 1 },
  aiDot:         { width: 8, height: 8, borderRadius: 4, flexShrink: 0 },
  aiKeyLabel:    { fontSize: 12, fontWeight: "700" },
  aiKeyModel:    { fontSize: 10, marginTop: 2, fontFamily: "monospace" },
  aiProvBadge:   { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 },
  aiProvBadgeTxt:{ fontSize: 9, fontWeight: "700" },
  aiStats:       { flexDirection: "row", gap: 8, marginTop: 4 },
  aiStat:        { fontSize: 10 },
  availBadge:    { paddingHorizontal: 8, paddingVertical: 4, borderRadius: 8 },
  availBadgeTxt: { fontSize: 10, fontWeight: "700" },
  aiSummary:     { borderTopWidth: 1, paddingTop: 8, marginTop: 4 },
  aiSummaryTxt:  { fontSize: 11, textAlign: "center" },

  patternRow:    { flexDirection: "row", alignItems: "center", gap: 8 },
  patternName:   { fontSize: 12, fontWeight: "600", width: 100 },
  patternBarWrap:{ flex: 1, height: 6, backgroundColor: "#33333322", borderRadius: 3, overflow: "hidden" },
  patternBar:    { height: 6, borderRadius: 3 },
  patternWr:     { fontSize: 11, fontWeight: "700", width: 36, textAlign: "right" },
  patternTotal:  { fontSize: 10, width: 24 },

  lessonRow:     { flexDirection: "row", gap: 8, padding: 10, borderRadius: 10, borderWidth: 1 },
  lessonIcon:    { fontSize: 14, marginTop: 1 },
  lessonTxt:     { fontSize: 12, lineHeight: 18 },
  lessonMeta:    { flexDirection: "row", gap: 8, marginTop: 4 },
  lessonMetaTxt: { fontSize: 10 },

  thoughtRow:    { borderLeftWidth: 3, paddingLeft: 10, paddingVertical: 6, paddingHorizontal: 10, borderRadius: 6 },
  thoughtTxt:    { fontSize: 11, fontFamily: "monospace", lineHeight: 16 },
  noThoughts:    { fontSize: 12, textAlign: "center", padding: 8 },

  emptyBox:      { alignItems: "center", gap: 6, paddingVertical: 16 },
  emptyTxt:      { fontSize: 14, fontWeight: "600" },
  emptySub:      { fontSize: 12 },
  msg:           { fontSize: 12, textAlign: "center", marginTop: 4 },

  // ── Brain Chat ─────────────────────────────────────────────────────────────
  chatContainer: {},
  chatMsgWrap:   { marginBottom: 6 },
  chatUserWrap:  { alignItems: "flex-end" },
  chatBotWrap:   { alignItems: "flex-start", flexDirection: "row", gap: 6 },
  chatAvatar:    { width: 20, height: 20, borderRadius: 5, alignItems: "center", justifyContent: "center", marginTop: 3, flexShrink: 0 },
  chatBubble:    { paddingHorizontal: 12, paddingVertical: 8, borderRadius: 14 },
  chatUserBubble:{ borderBottomRightRadius: 3 },
  chatBotBubble: { borderWidth: 1, borderBottomLeftRadius: 3, flexDirection: "row", alignItems: "center", gap: 8 },
  chatBubbleTxt: { fontSize: 13, lineHeight: 20 },
  chatTyping:    { fontSize: 12 },
  cmdBadge:      { flexDirection: "row", alignItems: "center", gap: 4, marginLeft: 4 },
  cmdBadgeTxt:   { fontSize: 9, color: "#10B981", fontWeight: "700" },
  chip:          { paddingHorizontal: 10, paddingVertical: 6, borderRadius: 16, borderWidth: 1, flexShrink: 0 },
  chipTxt:       { fontSize: 11, fontWeight: "600" },
  chatInputRow:  { flexDirection: "row", alignItems: "flex-end", gap: 8, paddingHorizontal: 12, paddingTop: 8, borderTopWidth: 1 },
  chatInput:     { flex: 1, borderRadius: 18, borderWidth: 1, paddingHorizontal: 14, paddingVertical: 9, fontSize: 13, maxHeight: 90 },
  chatSendBtn:   { width: 40, height: 40, borderRadius: 20, alignItems: "center", justifyContent: "center" },
});

// ── Memory & Knowledge Styles ──────────────────────────────────────────────────
const ms = StyleSheet.create({
  statCard:      { padding: 8, borderRadius: 10, borderWidth: 1, alignItems: "center", gap: 3 },
  statNum:       { fontSize: 16, fontWeight: "800" },
  statLabel:     { fontSize: 9, fontWeight: "600", textTransform: "uppercase", letterSpacing: 0.5 },

  searchRow:     { flexDirection: "row", alignItems: "center", gap: 8, paddingHorizontal: 12, paddingVertical: 10, borderRadius: 12, borderWidth: 1, marginBottom: 8 },
  searchInput:   { flex: 1, fontSize: 13 },

  tabRow:        { flexDirection: "row", gap: 8, marginBottom: 10 },
  tabBtn:        { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, paddingVertical: 9, paddingHorizontal: 12, borderRadius: 10 },
  tabBtnTxt:     { fontSize: 12 },

  lessonCard:    { flexDirection: "row", gap: 8, padding: 10, borderRadius: 10, borderWidth: 1 },
  lessonIcon:    { fontSize: 14, marginTop: 2 },
  lessonText:    { fontSize: 12, lineHeight: 18 },
  lessonFooter:  { flexDirection: "row", gap: 6, marginTop: 4, alignItems: "center", flexWrap: "wrap" },
  lessonTag:     { fontSize: 10, borderRadius: 4, borderWidth: 1, paddingHorizontal: 5, paddingVertical: 1 },
  lessonDate:    { fontSize: 9, marginLeft: "auto" },

  knowCard:      { flexDirection: "row", gap: 8, padding: 10, borderRadius: 10, borderWidth: 1 },
  knowTitle:     { fontSize: 12, fontWeight: "700", flex: 1 },
  knowContent:   { fontSize: 11, lineHeight: 17, marginTop: 3 },
  knowSource:    { fontSize: 9, marginTop: 3 },
  knowImp:       { fontSize: 9, marginLeft: "auto" },

  catDot:        { width: 8, height: 8, borderRadius: 4, flexShrink: 0 },
  catBadge:      { paddingHorizontal: 5, paddingVertical: 2, borderRadius: 4 },
  catBadgeTxt:   { fontSize: 9, fontWeight: "600" },

  addNoteBtn:    { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, padding: 10, borderRadius: 10, borderWidth: 1.5, borderStyle: "dashed" },
  addNoteTxt:    { fontSize: 13, fontWeight: "600" },
  addNoteForm:   { borderRadius: 12, borderWidth: 1, padding: 12, gap: 8 },
  noteInput:     { borderRadius: 8, borderWidth: 1, paddingHorizontal: 12, paddingVertical: 9, fontSize: 13 },
  noteInputMulti:{ minHeight: 70, textAlignVertical: "top" },
  catBtn:        { paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8, borderWidth: 1 },
  catBtnTxt:     { fontSize: 11, fontWeight: "600" },
  saveNoteBtn:   { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, paddingVertical: 10, borderRadius: 10 },
  saveNoteTxt:   { fontSize: 13, fontWeight: "700", color: "#fff" },

  emptyMem:      { alignItems: "center", gap: 8, paddingVertical: 24 },
  emptyMemTxt:   { fontSize: 14, fontWeight: "600" },
  emptyMemSub:   { fontSize: 12 },
});
