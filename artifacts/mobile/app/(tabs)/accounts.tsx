/**
 * Accounts Tab — حسابات بورصة بلا حدود
 * إضافة وإدارة عدد غير محدود من حسابات البورصات من نفس السيرفر
 */
import { Feather } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import React, { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  FlatList,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { getApiBase, safeJson } from "@/constants/api";
import { useColors } from "@/hooks/useColors";

const GREEN  = "#00C853";
const YELLOW = "#F59E0B";
const RED    = "#EF4444";
const BLUE   = "#3B82F6";
const PURPLE = "#8B5CF6";

// ─── Types ────────────────────────────────────────────────────────────────────

interface ExchangeAccount {
  id:            string;
  name:          string;
  exchange_name: string;
  mode:          string;
  is_active:     boolean;
  balance:       number;
  live_balance?: number;
  api_key?:      string;
  created_at?:   string;
}

const EXCHANGES = [
  { id: "mexc",    label: "MEXC",    color: "#00B4D8" },
  { id: "bybit",   label: "Bybit",   color: "#F7A600" },
  { id: "binance", label: "Binance", color: "#F0B90B" },
  { id: "kucoin",  label: "KuCoin",  color: "#00B574" },
  { id: "gate",    label: "Gate.io", color: "#2354E6" },
  { id: "okx",     label: "OKX",     color: "#FFFFFF" },
  { id: "huobi",   label: "HTX",     color: "#2773F5" },
];

// ─── Add Account Modal ────────────────────────────────────────────────────────

function AddAccountModal({
  visible,
  onClose,
  onAdded,
}: {
  visible: boolean;
  onClose: () => void;
  onAdded: () => void;
}) {
  const colors = useColors();
  const [name,       setName]       = useState("");
  const [exchange,   setExchange]   = useState("mexc");
  const [apiKey,     setApiKey]     = useState("");
  const [apiSecret,  setApiSecret]  = useState("");
  const [passphrase, setPassphrase] = useState("");
  const [mode,       setMode]       = useState<"demo" | "live">("demo");
  const [balance,    setBalance]    = useState("10000");
  const [loading,    setLoading]    = useState(false);
  const [msg,        setMsg]        = useState("");

  const reset = () => {
    setName(""); setExchange("mexc"); setApiKey(""); setApiSecret("");
    setPassphrase(""); setMode("demo"); setBalance("10000"); setMsg("");
  };

  const handleAdd = async () => {
    if (!name.trim()) { setMsg("❌ أدخل اسم الحساب"); return; }
    setLoading(true);
    try {
      const r = await fetch(`${getApiBase()}/accounts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name:           name.trim(),
          exchange_name:  exchange,
          api_key:        apiKey.trim(),
          api_secret:     apiSecret.trim(),
          api_passphrase: passphrase.trim(),
          mode,
          balance:        parseFloat(balance) || 10000,
        }),
      });
      const d = await safeJson(r);
      if (d?.success) {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        setMsg("✅ تمت الإضافة!");
        setTimeout(() => { reset(); onClose(); onAdded(); }, 800);
      } else {
        setMsg("❌ فشل إضافة الحساب");
      }
    } catch (e: any) {
      setMsg(`❌ ${e.message?.slice(0, 60)}`);
    }
    setLoading(false);
  };

  const selectedEx = EXCHANGES.find(e => e.id === exchange);

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={onClose}>
      <KeyboardAvoidingView
        style={[am.root, { backgroundColor: colors.background }]}
        behavior={Platform.OS === "ios" ? "padding" : "padding"}
        keyboardVerticalOffset={0}
      >
        {/* Header */}
        <View style={[am.header, { borderBottomColor: colors.border }]}>
          <Pressable onPress={() => { reset(); onClose(); }} style={am.closeBtn}>
            <Feather name="x" size={22} color={colors.foreground} />
          </Pressable>
          <Text style={[am.title, { color: colors.foreground }]}>➕ حساب بورصة جديد</Text>
          <View style={{ width: 38 }} />
        </View>

        <ScrollView style={{ flex: 1, padding: 18 }} keyboardDismissMode="on-drag" showsVerticalScrollIndicator={false}>

          {/* Name */}
          <Text style={[am.label, { color: colors.mutedForeground }]}>اسم الحساب *</Text>
          <TextInput
            style={[am.input, { color: colors.foreground, borderColor: colors.border, backgroundColor: colors.card }]}
            value={name} onChangeText={setName}
            placeholder="مثال: Bybit رئيسي، Binance احتياطي..." placeholderTextColor={colors.mutedForeground}
          />

          {/* Exchange picker */}
          <Text style={[am.label, { color: colors.mutedForeground }]}>اختر البورصة</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 18 }}>
            {EXCHANGES.map(ex => {
              const sel = exchange === ex.id;
              return (
                <Pressable
                  key={ex.id}
                  onPress={() => setExchange(ex.id)}
                  style={[am.exChip, {
                    backgroundColor: sel ? ex.color + "20" : colors.card,
                    borderColor:     sel ? ex.color : colors.border,
                  }]}
                >
                  <Text style={[am.exChipTxt, { color: sel ? ex.color : colors.mutedForeground }]}>
                    {ex.label}
                  </Text>
                  {sel && <View style={[am.exDot, { backgroundColor: ex.color }]} />}
                </Pressable>
              );
            })}
          </ScrollView>

          {/* Mode */}
          <Text style={[am.label, { color: colors.mutedForeground }]}>وضع التداول</Text>
          <View style={{ flexDirection: "row", gap: 10, marginBottom: 18 }}>
            {(["demo", "live"] as const).map(m => {
              const sel   = mode === m;
              const color = m === "live" ? GREEN : YELLOW;
              return (
                <Pressable
                  key={m}
                  onPress={() => setMode(m)}
                  style={[am.modeChip, {
                    flex: 1,
                    backgroundColor: sel ? color + "18" : colors.card,
                    borderColor:     sel ? color : colors.border,
                  }]}
                >
                  <Text style={{ fontSize: 18 }}>{m === "demo" ? "📄" : "💰"}</Text>
                  <Text style={[am.modeTxt, { color: sel ? color : colors.mutedForeground }]}>
                    {m === "demo" ? "ورقي Demo" : "حقيقي Live"}
                  </Text>
                </Pressable>
              );
            })}
          </View>

          {/* API Key */}
          <Text style={[am.label, { color: colors.mutedForeground }]}>
            API Key {mode === "demo" ? "(اختياري في Demo)" : "*"}
          </Text>
          <TextInput
            style={[am.input, { color: colors.foreground, borderColor: colors.border, backgroundColor: colors.card }]}
            value={apiKey} onChangeText={setApiKey}
            placeholder="sk-..." placeholderTextColor={colors.mutedForeground}
            autoCapitalize="none" autoCorrect={false}
          />

          {/* API Secret */}
          <Text style={[am.label, { color: colors.mutedForeground }]}>
            API Secret {mode === "demo" ? "(اختياري)" : "*"}
          </Text>
          <TextInput
            style={[am.input, { color: colors.foreground, borderColor: colors.border, backgroundColor: colors.card }]}
            value={apiSecret} onChangeText={setApiSecret}
            placeholder="secret..." placeholderTextColor={colors.mutedForeground}
            autoCapitalize="none" autoCorrect={false} secureTextEntry
          />

          {/* Passphrase for KuCoin/OKX */}
          {(exchange === "kucoin" || exchange === "okx") && (
            <>
              <Text style={[am.label, { color: colors.mutedForeground }]}>Passphrase</Text>
              <TextInput
                style={[am.input, { color: colors.foreground, borderColor: colors.border, backgroundColor: colors.card }]}
                value={passphrase} onChangeText={setPassphrase}
                placeholder="passphrase..." placeholderTextColor={colors.mutedForeground}
                autoCapitalize="none" secureTextEntry
              />
            </>
          )}

          {/* Demo balance */}
          {mode === "demo" && (
            <>
              <Text style={[am.label, { color: colors.mutedForeground }]}>رصيد البداية الورقي (USDT)</Text>
              <TextInput
                style={[am.input, { color: colors.foreground, borderColor: colors.border, backgroundColor: colors.card }]}
                value={balance} onChangeText={setBalance}
                placeholder="10000" placeholderTextColor={colors.mutedForeground}
                keyboardType="numeric"
              />
            </>
          )}

          {/* Message */}
          {!!msg && (
            <View style={[am.msgBox, { backgroundColor: msg.startsWith("✅") ? GREEN + "15" : RED + "15" }]}>
              <Text style={{ color: msg.startsWith("✅") ? GREEN : RED, fontSize: 13, fontWeight: "600" }}>{msg}</Text>
            </View>
          )}

          {/* Halal note */}
          <View style={[am.halalBox, { backgroundColor: GREEN + "10", borderColor: GREEN + "30" }]}>
            <Text style={[am.halalTxt, { color: colors.mutedForeground }]}>
              ☪️ حلال — Spot فقط • لا رافعة مالية • لا هامش{"\n"}
              🔒 مفاتيح API محفوظة في قاعدة بياناتك الخاصة فقط
            </Text>
          </View>
        </ScrollView>

        {/* Footer */}
        <View style={[am.footer, { borderTopColor: colors.border, backgroundColor: colors.background }]}>
          <Pressable
            style={[am.addBtn, { backgroundColor: selectedEx?.color || GREEN, opacity: loading ? 0.65 : 1 }]}
            onPress={handleAdd}
            disabled={loading}
          >
            {loading
              ? <ActivityIndicator size="small" color="#000" />
              : <Text style={am.addBtnTxt}>➕ إضافة {selectedEx?.label || ""}</Text>
            }
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const am = StyleSheet.create({
  root:      { flex: 1 },
  header:    { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: 18, paddingVertical: 14, borderBottomWidth: 1 },
  closeBtn:  { padding: 6 },
  title:     { fontSize: 16, fontWeight: "800" },
  label:     { fontSize: 11, fontWeight: "700", letterSpacing: 0.8, marginBottom: 7, marginTop: 2 },
  input:     { borderWidth: 1, borderRadius: 12, padding: 13, fontSize: 14, marginBottom: 16 },
  exChip:    { paddingHorizontal: 14, paddingVertical: 9, borderRadius: 10, borderWidth: 1.5, marginRight: 8, flexDirection: "row", alignItems: "center", gap: 5 },
  exChipTxt: { fontSize: 12, fontWeight: "800" },
  exDot:     { width: 5, height: 5, borderRadius: 3 },
  modeChip:  { borderRadius: 12, borderWidth: 1.5, padding: 14, alignItems: "center", gap: 4 },
  modeTxt:   { fontSize: 12, fontWeight: "700" },
  msgBox:    { padding: 12, borderRadius: 10, marginBottom: 12 },
  halalBox:  { borderRadius: 12, borderWidth: 1, padding: 14, marginBottom: 24 },
  halalTxt:  { fontSize: 12, lineHeight: 19, fontWeight: "500" },
  footer:    { padding: 18, borderTopWidth: 1 },
  addBtn:    { borderRadius: 14, height: 54, alignItems: "center", justifyContent: "center" },
  addBtnTxt: { fontSize: 15, fontWeight: "800", color: "#000" },
});

// ─── Account Card ─────────────────────────────────────────────────────────────

function AccountCard({
  account,
  onToggle,
  onDelete,
}: {
  account:  ExchangeAccount;
  onToggle: (id: string, active: boolean) => void;
  onDelete: (id: string, name: string) => void;
}) {
  const colors   = useColors();
  const balance  = account.live_balance ?? account.balance;
  const exInfo   = EXCHANGES.find(e => e.id === account.exchange_name) ?? { color: "#888", label: account.exchange_name.toUpperCase() };
  const modeClr  = account.mode === "live" ? GREEN : YELLOW;

  return (
    <View style={[card.wrap, { backgroundColor: colors.card, borderColor: colors.border }]}>
      {/* Top row */}
      <View style={card.row}>
        <View style={[card.exBadge, { backgroundColor: exInfo.color + "18", borderColor: exInfo.color + "60" }]}>
          <Text style={[card.exTxt, { color: exInfo.color }]}>{exInfo.label}</Text>
        </View>
        <View style={{ flex: 1, marginLeft: 10 }}>
          <Text style={[card.name, { color: colors.foreground }]} numberOfLines={1}>{account.name}</Text>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 6, marginTop: 3 }}>
            <View style={[card.modeBadge, { backgroundColor: modeClr + "18" }]}>
              <Text style={[card.modeTxt, { color: modeClr }]}>
                {account.mode === "live" ? "💰 Live" : "📄 Demo"}
              </Text>
            </View>
            <Text style={[card.spot, { color: colors.mutedForeground }]}>• Spot ✓</Text>
          </View>
        </View>
        <Switch
          value={account.is_active}
          onValueChange={v => onToggle(account.id, v)}
          trackColor={{ false: "#333", true: GREEN + "88" }}
          thumbColor={account.is_active ? GREEN : "#555"}
        />
      </View>

      {/* Divider */}
      <View style={[card.div, { backgroundColor: colors.border }]} />

      {/* Bottom row */}
      <View style={card.row}>
        <View>
          <Text style={[card.balLbl, { color: colors.mutedForeground }]}>الرصيد (USDT)</Text>
          <Text style={[card.balVal, { color: account.is_active ? GREEN : colors.mutedForeground }]}>
            ${balance.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </Text>
        </View>
        <View style={{ flexDirection: "row", gap: 8 }}>
          {!account.is_active && (
            <View style={[card.offlineBadge, { borderColor: colors.border }]}>
              <Text style={[card.offlineTxt, { color: colors.mutedForeground }]}>موقف</Text>
            </View>
          )}
          <Pressable
            style={[card.delBtn, { borderColor: RED + "60" }]}
            onPress={() => onDelete(account.id, account.name)}
          >
            <Feather name="trash-2" size={15} color={RED} />
          </Pressable>
        </View>
      </View>
    </View>
  );
}

const card = StyleSheet.create({
  wrap:        { borderRadius: 16, borderWidth: 1, marginBottom: 12, padding: 15 },
  row:         { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  exBadge:     { paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8, borderWidth: 1 },
  exTxt:       { fontSize: 11, fontWeight: "800", letterSpacing: 0.5 },
  name:        { fontSize: 14, fontWeight: "700", maxWidth: 160 },
  modeBadge:   { paddingHorizontal: 7, paddingVertical: 2, borderRadius: 5 },
  modeTxt:     { fontSize: 10, fontWeight: "700" },
  spot:        { fontSize: 10 },
  div:         { height: 1, marginVertical: 12 },
  balLbl:      { fontSize: 10, fontWeight: "600", marginBottom: 2 },
  balVal:      { fontSize: 18, fontWeight: "800" },
  offlineBadge:{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6, borderWidth: 1 },
  offlineTxt:  { fontSize: 10, fontWeight: "600" },
  delBtn:      { width: 34, height: 34, borderRadius: 9, borderWidth: 1, alignItems: "center", justifyContent: "center" },
});

// ─── Empty State ──────────────────────────────────────────────────────────────

function EmptyState({ onAdd }: { onAdd: () => void }) {
  const colors = useColors();
  return (
    <View style={[empty.wrap, { backgroundColor: colors.card, borderColor: colors.border }]}>
      <Text style={empty.icon}>🏦</Text>
      <Text style={[empty.title, { color: colors.foreground }]}>لا توجد حسابات بعد</Text>
      <Text style={[empty.sub, { color: colors.mutedForeground }]}>
        أضف حسابات من بورصات متعددة — MEXC، Bybit، Binance وغيرها.{"\n"}
        البوت سيُنفّذ نفس الصفقة تلقائياً على جميع الحسابات في نفس اللحظة.
      </Text>
      <Pressable style={[empty.btn, { backgroundColor: GREEN }]} onPress={onAdd}>
        <Text style={empty.btnTxt}>➕ أضف أول حساب</Text>
      </Pressable>
    </View>
  );
}

const empty = StyleSheet.create({
  wrap:   { borderRadius: 18, borderWidth: 1, padding: 28, alignItems: "center", marginTop: 10 },
  icon:   { fontSize: 48, marginBottom: 12 },
  title:  { fontSize: 18, fontWeight: "800", marginBottom: 8 },
  sub:    { fontSize: 13, textAlign: "center", lineHeight: 20, marginBottom: 20 },
  btn:    { paddingHorizontal: 24, paddingVertical: 12, borderRadius: 12 },
  btnTxt: { fontSize: 14, fontWeight: "800", color: "#000" },
});

// ─── How It Works ─────────────────────────────────────────────────────────────

function HowItWorks() {
  const colors = useColors();
  const steps = [
    { icon: "🤖", title: "البوت يحلّل", desc: "الذكاء الاصطناعي يحلّل السوق ويأخذ قرار الشراء" },
    { icon: "⚡", title: "تنفيذ فوري", desc: "نفس الأمر يُرسَل لكل حساباتك في نفس اللحظة" },
    { icon: "💰", title: "أرباح مضاعفة", desc: "كل حساب يُغلق الصفقة باستقلالية مع تتبع كامل" },
  ];
  return (
    <View style={{ marginBottom: 24 }}>
      <Text style={[hw.title, { color: colors.mutedForeground }]}>⚡ كيف يعمل التداول متعدد الحسابات</Text>
      <View style={[hw.card, { backgroundColor: colors.card, borderColor: colors.border }]}>
        {steps.map((s, i) => (
          <View key={i} style={[hw.step, i < steps.length - 1 && { borderBottomWidth: 1, borderBottomColor: colors.border }]}>
            <Text style={hw.stepIcon}>{s.icon}</Text>
            <View style={{ flex: 1 }}>
              <Text style={[hw.stepTitle, { color: colors.foreground }]}>{s.title}</Text>
              <Text style={[hw.stepDesc, { color: colors.mutedForeground }]}>{s.desc}</Text>
            </View>
            {i < steps.length - 1 && (
              <Feather name="arrow-down" size={14} color={colors.mutedForeground} />
            )}
          </View>
        ))}
      </View>
    </View>
  );
}

const hw = StyleSheet.create({
  title:     { fontSize: 11, fontWeight: "700", letterSpacing: 0.8, marginBottom: 10 },
  card:      { borderRadius: 14, borderWidth: 1, overflow: "hidden" },
  step:      { flexDirection: "row", alignItems: "center", gap: 12, padding: 14 },
  stepIcon:  { fontSize: 22 },
  stepTitle: { fontSize: 13, fontWeight: "700", marginBottom: 2 },
  stepDesc:  { fontSize: 11, lineHeight: 16 },
});

// ─── Main Screen ──────────────────────────────────────────────────────────────

export default function AccountsScreen() {
  const colors   = useColors();
  const insets   = useSafeAreaInsets();

  const [accounts,   setAccounts]   = useState<ExchangeAccount[]>([]);
  const [loading,    setLoading]    = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [showAdd,    setShowAdd]    = useState(false);
  const [balLoading, setBalLoading] = useState(false);
  const [totalBal,   setTotalBal]   = useState(0);
  const [lastSync,   setLastSync]   = useState("");

  const fetchAccounts = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    try {
      const _c1 = new AbortController(); setTimeout(() => _c1.abort(), 8000);
      const r = await fetch(`${getApiBase()}/accounts`, { signal: _c1.signal });
      const d = await safeJson(r);
      if (d?.accounts) {
        setAccounts(d.accounts);
      }
    } catch {}
    if (!quiet) setLoading(false);
  }, []);

  const fetchBalances = useCallback(async () => {
    setBalLoading(true);
    try {
      const _c2 = new AbortController(); setTimeout(() => _c2.abort(), 15000);
      const r = await fetch(`${getApiBase()}/accounts/balances`, { signal: _c2.signal });
      const d = await safeJson(r);
      if (d?.accounts) {
        const map: Record<string, number> = {};
        for (const b of d.accounts) {
          if (b.account_id) map[b.account_id] = b.total ?? 0;
        }
        setAccounts(prev => prev.map(a => ({ ...a, live_balance: map[a.id] ?? a.live_balance })));
        setTotalBal(d.total_combined_usdt ?? 0);
        setLastSync(new Date().toLocaleTimeString("ar-SA"));
        Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
      }
    } catch {}
    setBalLoading(false);
  }, []);

  useEffect(() => {
    fetchAccounts();
  }, [fetchAccounts]);

  const onRefresh = async () => {
    setRefreshing(true);
    await fetchAccounts(true);
    setRefreshing(false);
  };

  const handleToggle = async (id: string, active: boolean) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setAccounts(prev => prev.map(a => a.id === id ? { ...a, is_active: active } : a));
    try {
      await fetch(`${getApiBase()}/accounts/${id}/toggle`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: active }),
      });
    } catch {}
  };

  const handleDelete = (id: string, name: string) => {
    Alert.alert(
      "حذف الحساب",
      `هل تريد حذف "${name}"؟ لن تؤثر صفقاته المفتوحة بالبورصة الفعلية.`,
      [
        { text: "إلغاء", style: "cancel" },
        {
          text: "حذف",
          style: "destructive",
          onPress: async () => {
            Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
            setAccounts(prev => prev.filter(a => a.id !== id));
            try {
              await fetch(`${getApiBase()}/accounts/${id}`, { method: "DELETE" });
            } catch {}
          },
        },
      ]
    );
  };

  const activeCount   = accounts.filter(a => a.is_active).length;
  const totalAccounts = accounts.length;
  const liveCount     = accounts.filter(a => a.mode === "live").length;

  return (
    <View style={[s.root, { backgroundColor: colors.background }]}>
      {/* ── Header ── */}
      <View style={[s.header, { paddingTop: insets.top + 12, borderBottomColor: colors.border }]}>
        <View>
          <Text style={[s.title, { color: colors.foreground }]}>🏦 حسابات البورصات</Text>
          <Text style={[s.subtitle, { color: colors.mutedForeground }]}>
            تداول واحد → {totalAccounts > 0 ? totalAccounts : "∞"} حساب
          </Text>
        </View>
        <Pressable
          style={[s.addHeaderBtn, { backgroundColor: GREEN }]}
          onPress={() => setShowAdd(true)}
        >
          <Feather name="plus" size={18} color="#000" />
          <Text style={s.addHeaderBtnTxt}>إضافة</Text>
        </Pressable>
      </View>

      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ padding: 16, paddingBottom: insets.bottom + 100 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={GREEN} />}
        showsVerticalScrollIndicator={false}
      >
        {/* ── Stats Row ── */}
        <View style={s.statsRow}>
          <View style={[s.statCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
            <Text style={[s.statVal, { color: GREEN }]}>{totalAccounts}</Text>
            <Text style={[s.statLbl, { color: colors.mutedForeground }]}>إجمالي</Text>
          </View>
          <View style={[s.statCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
            <Text style={[s.statVal, { color: activeCount > 0 ? GREEN : RED }]}>{activeCount}</Text>
            <Text style={[s.statLbl, { color: colors.mutedForeground }]}>مفعّل</Text>
          </View>
          <View style={[s.statCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
            <Text style={[s.statVal, { color: liveCount > 0 ? GREEN : YELLOW }]}>{liveCount}</Text>
            <Text style={[s.statLbl, { color: colors.mutedForeground }]}>حقيقي</Text>
          </View>
          <View style={[s.statCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
            <Text style={[s.statVal, { color: PURPLE }]}>∞</Text>
            <Text style={[s.statLbl, { color: colors.mutedForeground }]}>بلا حدود</Text>
          </View>
        </View>

        {/* ── Combined Balance ── */}
        {totalBal > 0 && (
          <View style={[s.balCard, { backgroundColor: GREEN + "12", borderColor: GREEN + "35" }]}>
            <View>
              <Text style={[s.balTitle, { color: colors.mutedForeground }]}>إجمالي رصيد الحسابات المُفعَّلة</Text>
              <Text style={[s.balValue, { color: GREEN }]}>
                ${totalBal.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USDT
              </Text>
              {lastSync && (
                <Text style={[s.syncTime, { color: colors.mutedForeground }]}>آخر تحديث: {lastSync}</Text>
              )}
            </View>
            <Pressable
              style={[s.syncBtn, { borderColor: GREEN, opacity: balLoading ? 0.5 : 1 }]}
              onPress={fetchBalances}
              disabled={balLoading}
            >
              {balLoading
                ? <ActivityIndicator size="small" color={GREEN} />
                : <Feather name="refresh-cw" size={18} color={GREEN} />
              }
            </Pressable>
          </View>
        )}

        {/* ── Accounts List ── */}
        <View style={s.section}>
          <View style={s.sectionRow}>
            <Text style={[s.sectionTitle, { color: colors.mutedForeground }]}>
              حساباتك ({totalAccounts})
            </Text>
            {totalAccounts > 0 && (
              <Pressable
                style={[s.balBtn, { borderColor: BLUE, opacity: balLoading ? 0.5 : 1 }]}
                onPress={fetchBalances}
                disabled={balLoading}
              >
                {balLoading
                  ? <ActivityIndicator size="small" color={BLUE} />
                  : <Feather name="refresh-cw" size={12} color={BLUE} />
                }
                <Text style={[s.balBtnTxt, { color: BLUE }]}>تحديث الأرصدة</Text>
              </Pressable>
            )}
          </View>

          {loading ? (
            <View style={s.loadingWrap}>
              <ActivityIndicator color={GREEN} size="large" />
              <Text style={[s.loadingTxt, { color: colors.mutedForeground }]}>جارٍ التحميل...</Text>
            </View>
          ) : accounts.length === 0 ? (
            <EmptyState onAdd={() => setShowAdd(true)} />
          ) : (
            accounts.map(acc => (
              <AccountCard
                key={acc.id}
                account={acc}
                onToggle={handleToggle}
                onDelete={handleDelete}
              />
            ))
          )}
        </View>

        {/* ── How it works ── */}
        <HowItWorks />

        {/* ── Supported Exchanges ── */}
        <View style={{ marginBottom: 20 }}>
          <Text style={[s.sectionTitle, { color: colors.mutedForeground, marginBottom: 10 }]}>
            البورصات المدعومة
          </Text>
          <View style={s.exRow}>
            {EXCHANGES.map(ex => (
              <View key={ex.id} style={[s.exTag, { backgroundColor: ex.color + "18", borderColor: ex.color + "50" }]}>
                <Text style={[s.exTagTxt, { color: ex.color }]}>{ex.label}</Text>
              </View>
            ))}
          </View>
          <Text style={[s.exNote, { color: colors.mutedForeground }]}>
            + أي بورصة تدعم CCXT • يمكن إضافة عدد غير محدود من الحسابات لكل بورصة
          </Text>
        </View>
      </ScrollView>

      <AddAccountModal
        visible={showAdd}
        onClose={() => setShowAdd(false)}
        onAdded={fetchAccounts}
      />
    </View>
  );
}

const s = StyleSheet.create({
  root:         { flex: 1 },
  header:       { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: 18, paddingBottom: 14, borderBottomWidth: 1 },
  title:        { fontSize: 20, fontWeight: "800" },
  subtitle:     { fontSize: 11, marginTop: 2, letterSpacing: 0.4 },
  addHeaderBtn: { flexDirection: "row", alignItems: "center", gap: 5, paddingHorizontal: 14, paddingVertical: 9, borderRadius: 12 },
  addHeaderBtnTxt: { fontSize: 13, fontWeight: "700", color: "#000" },
  statsRow:     { flexDirection: "row", gap: 8, marginBottom: 14 },
  statCard:     { flex: 1, borderRadius: 12, borderWidth: 1, padding: 12, alignItems: "center" },
  statVal:      { fontSize: 20, fontWeight: "800" },
  statLbl:      { fontSize: 9, fontWeight: "600", marginTop: 2, letterSpacing: 0.4 },
  balCard:      { flexDirection: "row", alignItems: "center", justifyContent: "space-between", borderRadius: 14, borderWidth: 1, padding: 16, marginBottom: 20 },
  balTitle:     { fontSize: 10, fontWeight: "700", letterSpacing: 0.5, marginBottom: 4 },
  balValue:     { fontSize: 22, fontWeight: "800" },
  syncTime:     { fontSize: 10, marginTop: 4 },
  syncBtn:      { width: 42, height: 42, borderRadius: 12, borderWidth: 1.5, alignItems: "center", justifyContent: "center" },
  section:      { marginBottom: 24 },
  sectionRow:   { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 12 },
  sectionTitle: { fontSize: 11, fontWeight: "700", letterSpacing: 0.8 },
  balBtn:       { flexDirection: "row", alignItems: "center", gap: 5, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, borderWidth: 1 },
  balBtnTxt:    { fontSize: 11, fontWeight: "700" },
  loadingWrap:  { padding: 40, alignItems: "center", gap: 12 },
  loadingTxt:   { fontSize: 13 },
  exRow:        { flexDirection: "row", flexWrap: "wrap", gap: 8, marginBottom: 10 },
  exTag:        { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, borderWidth: 1 },
  exTagTxt:     { fontSize: 12, fontWeight: "700" },
  exNote:       { fontSize: 11, lineHeight: 17 },
});
