/**
 * Accounts Tab — Multi-Account Trading + Multi-Server Cluster
 * Manage multiple exchange accounts & view server cluster status
 */
import { Feather } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import React, { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Modal,
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
const DARK   = "#0A0A0A";

// ─── Types ────────────────────────────────────────────────────────────────────

interface ExchangeAccount {
  id:            string;
  name:          string;
  exchange_name: string;
  mode:          string;
  is_active:     boolean;
  balance:       number;
  live_balance?: number;
  created_at?:   string;
}

interface ServerNode {
  node_id:        string;
  hostname:       string;
  is_leader:      boolean;
  last_heartbeat: string;
  age_seconds:    number;
  alive:          boolean;
}

const EXCHANGES = ["mexc", "bybit", "binance", "kucoin", "gate", "okx", "huobi"];

// ─── Add Account Modal ────────────────────────────────────────────────────────

function AddAccountModal({
  visible,
  onClose,
  onAdded,
}: {
  visible:  boolean;
  onClose:  () => void;
  onAdded:  () => void;
}) {
  const colors = useColors();
  const [name,        setName]        = useState("");
  const [exchange,    setExchange]    = useState("mexc");
  const [apiKey,      setApiKey]      = useState("");
  const [apiSecret,   setApiSecret]   = useState("");
  const [passphrase,  setPassphrase]  = useState("");
  const [mode,        setMode]        = useState<"demo" | "live">("demo");
  const [balance,     setBalance]     = useState("10000");
  const [loading,     setLoading]     = useState(false);
  const [msg,         setMsg]         = useState("");

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
          name:          name.trim(),
          exchange_name: exchange,
          api_key:       apiKey.trim(),
          api_secret:    apiSecret.trim(),
          api_passphrase: passphrase.trim(),
          mode,
          balance:       parseFloat(balance) || 10000,
        }),
      });
      const d = await safeJson(r);
      if (d?.success) {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        reset();
        onClose();
        onAdded();
      } else {
        setMsg("❌ فشل إضافة الحساب");
      }
    } catch (e: any) {
      setMsg(`❌ ${e.message?.slice(0, 60)}`);
    }
    setLoading(false);
  };

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={onClose}>
      <View style={[am.root, { backgroundColor: colors.background }]}>
        <View style={[am.header, { borderBottomColor: colors.border }]}>
          <Pressable onPress={() => { reset(); onClose(); }} style={am.closeBtn}>
            <Feather name="x" size={20} color={colors.foreground} />
          </Pressable>
          <Text style={[am.title, { color: colors.foreground }]}>➕ حساب بورصة جديد</Text>
          <View style={{ width: 36 }} />
        </View>

        <ScrollView style={am.body} keyboardDismissMode="on-drag">
          {/* Name */}
          <Text style={[am.label, { color: colors.mutedForeground }]}>اسم الحساب *</Text>
          <TextInput
            style={[am.input, { color: colors.foreground, borderColor: colors.border, backgroundColor: colors.card }]}
            value={name} onChangeText={setName}
            placeholder="مثال: Bybit رئيسي" placeholderTextColor={colors.mutedForeground}
          />

          {/* Exchange */}
          <Text style={[am.label, { color: colors.mutedForeground }]}>البورصة</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 16 }}>
            {EXCHANGES.map(ex => (
              <Pressable
                key={ex}
                onPress={() => setExchange(ex)}
                style={[am.chip, {
                  backgroundColor: exchange === ex ? GREEN : colors.card,
                  borderColor:     exchange === ex ? GREEN : colors.border,
                }]}
              >
                <Text style={[am.chipTxt, { color: exchange === ex ? "#000" : colors.foreground }]}>
                  {ex.toUpperCase()}
                </Text>
              </Pressable>
            ))}
          </ScrollView>

          {/* Mode */}
          <Text style={[am.label, { color: colors.mutedForeground }]}>الوضع</Text>
          <View style={{ flexDirection: "row", gap: 10, marginBottom: 16 }}>
            {(["demo", "live"] as const).map(m => (
              <Pressable
                key={m}
                onPress={() => setMode(m)}
                style={[am.chip, {
                  flex:            1,
                  justifyContent:  "center",
                  backgroundColor: mode === m ? (m === "live" ? GREEN : YELLOW) : colors.card,
                  borderColor:     mode === m ? (m === "live" ? GREEN : YELLOW) : colors.border,
                }]}
              >
                <Text style={[am.chipTxt, { color: mode === m ? "#000" : colors.foreground, textAlign: "center" }]}>
                  {m === "demo" ? "📄 ورقي (Demo)" : "💰 حقيقي (Live)"}
                </Text>
              </Pressable>
            ))}
          </View>

          {/* API Key */}
          <Text style={[am.label, { color: colors.mutedForeground }]}>
            {mode === "demo" ? "API Key (اختياري في Demo)" : "API Key *"}
          </Text>
          <TextInput
            style={[am.input, { color: colors.foreground, borderColor: colors.border, backgroundColor: colors.card }]}
            value={apiKey} onChangeText={setApiKey}
            placeholder="sk-..." placeholderTextColor={colors.mutedForeground}
            autoCapitalize="none" autoCorrect={false}
          />

          {/* API Secret */}
          <Text style={[am.label, { color: colors.mutedForeground }]}>
            {mode === "demo" ? "API Secret (اختياري)" : "API Secret *"}
          </Text>
          <TextInput
            style={[am.input, { color: colors.foreground, borderColor: colors.border, backgroundColor: colors.card }]}
            value={apiSecret} onChangeText={setApiSecret}
            placeholder="secret..." placeholderTextColor={colors.mutedForeground}
            autoCapitalize="none" autoCorrect={false} secureTextEntry
          />

          {/* Passphrase (KuCoin etc) */}
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
              <Text style={[am.label, { color: colors.mutedForeground }]}>رصيد ورقي (USDT)</Text>
              <TextInput
                style={[am.input, { color: colors.foreground, borderColor: colors.border, backgroundColor: colors.card }]}
                value={balance} onChangeText={setBalance}
                placeholder="10000" placeholderTextColor={colors.mutedForeground}
                keyboardType="numeric"
              />
            </>
          )}

          {!!msg && (
            <View style={am.msgBox}>
              <Text style={{ color: msg.startsWith("✅") ? GREEN : RED, fontSize: 13 }}>{msg}</Text>
            </View>
          )}

          <View style={am.infoBox}>
            <Feather name="shield" size={13} color={YELLOW} />
            <Text style={[am.infoTxt, { color: colors.mutedForeground }]}>
              مفاتيح API محفوظة في قاعدة البيانات الخاصة بك فقط — حلال ✓ Spot فقط
            </Text>
          </View>
        </ScrollView>

        <View style={[am.footer, { borderTopColor: colors.border }]}>
          <Pressable
            style={[am.addBtn, { backgroundColor: GREEN, opacity: loading ? 0.6 : 1 }]}
            onPress={handleAdd} disabled={loading}
          >
            {loading
              ? <ActivityIndicator size="small" color="#000" />
              : <Text style={am.addBtnTxt}>➕ إضافة الحساب</Text>
            }
          </Pressable>
        </View>
      </View>
    </Modal>
  );
}

const am = StyleSheet.create({
  root:     { flex: 1 },
  header:   { flexDirection: "row", alignItems: "center", justifyContent: "space-between", padding: 16, borderBottomWidth: 1 },
  closeBtn: { padding: 8 },
  title:    { fontSize: 16, fontWeight: "700" },
  body:     { flex: 1, padding: 16 },
  label:    { fontSize: 11, fontWeight: "700", letterSpacing: 0.8, marginBottom: 6 },
  input:    { borderWidth: 1, borderRadius: 10, padding: 12, fontSize: 14, marginBottom: 16 },
  chip:     { paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8, borderWidth: 1, marginRight: 8 },
  chipTxt:  { fontSize: 12, fontWeight: "700" },
  msgBox:   { padding: 12, borderRadius: 10, backgroundColor: "#FF525215", marginBottom: 12 },
  infoBox:  { flexDirection: "row", gap: 8, padding: 12, borderRadius: 10, backgroundColor: "#F59E0B15", marginBottom: 24 },
  infoTxt:  { flex: 1, fontSize: 11, lineHeight: 16 },
  footer:   { padding: 16, borderTopWidth: 1 },
  addBtn:   { borderRadius: 14, height: 52, alignItems: "center", justifyContent: "center" },
  addBtnTxt: { fontSize: 15, fontWeight: "700", color: "#000" },
});

// ─── Account Card ─────────────────────────────────────────────────────────────

function AccountCard({
  account,
  onToggle,
  onDelete,
  onRefreshBalance,
}: {
  account:          ExchangeAccount;
  onToggle:         (id: string, active: boolean) => void;
  onDelete:         (id: string, name: string) => void;
  onRefreshBalance: () => void;
}) {
  const colors = useColors();
  const balance = account.live_balance ?? account.balance;
  const exColor = account.mode === "live" ? GREEN : YELLOW;

  return (
    <View style={[ac.card, { backgroundColor: colors.card, borderColor: colors.border }]}>
      <View style={ac.row}>
        <View style={ac.left}>
          <View style={[ac.badge, { backgroundColor: exColor + "20", borderColor: exColor }]}>
            <Text style={[ac.badgeTxt, { color: exColor }]}>
              {account.exchange_name.toUpperCase()}
            </Text>
          </View>
          <View>
            <Text style={[ac.name, { color: colors.foreground }]}>{account.name}</Text>
            <Text style={[ac.sub, { color: colors.mutedForeground }]}>
              {account.mode === "live" ? "💰 Live" : "📄 Demo"} • Spot Only ✓
            </Text>
          </View>
        </View>
        <Switch
          value={account.is_active}
          onValueChange={v => onToggle(account.id, v)}
          trackColor={{ false: "#333", true: GREEN + "99" }}
          thumbColor={account.is_active ? GREEN : "#666"}
        />
      </View>

      <View style={[ac.divider, { backgroundColor: colors.border }]} />

      <View style={ac.row}>
        <View>
          <Text style={[ac.balLabel, { color: colors.mutedForeground }]}>الرصيد</Text>
          <Text style={[ac.balValue, { color: account.is_active ? GREEN : colors.mutedForeground }]}>
            ${balance.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USDT
          </Text>
        </View>
        <View style={{ flexDirection: "row", gap: 8 }}>
          <Pressable
            style={[ac.iconBtn, { borderColor: BLUE }]}
            onPress={onRefreshBalance}
          >
            <Feather name="refresh-cw" size={14} color={BLUE} />
          </Pressable>
          <Pressable
            style={[ac.iconBtn, { borderColor: RED }]}
            onPress={() => onDelete(account.id, account.name)}
          >
            <Feather name="trash-2" size={14} color={RED} />
          </Pressable>
        </View>
      </View>
    </View>
  );
}

const ac = StyleSheet.create({
  card:      { borderRadius: 14, borderWidth: 1, marginBottom: 12, padding: 14 },
  row:       { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  left:      { flexDirection: "row", alignItems: "center", gap: 10, flex: 1 },
  badge:     { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, borderWidth: 1 },
  badgeTxt:  { fontSize: 10, fontWeight: "800", letterSpacing: 0.5 },
  name:      { fontSize: 14, fontWeight: "700" },
  sub:       { fontSize: 11, marginTop: 2 },
  divider:   { height: 1, marginVertical: 10 },
  balLabel:  { fontSize: 10, fontWeight: "600", letterSpacing: 0.5, marginBottom: 2 },
  balValue:  { fontSize: 16, fontWeight: "800" },
  iconBtn:   { width: 32, height: 32, borderRadius: 8, borderWidth: 1, alignItems: "center", justifyContent: "center" },
});

// ─── Cluster Node Row ─────────────────────────────────────────────────────────

function NodeRow({ node }: { node: ServerNode }) {
  const colors = useColors();
  const alive  = node.alive;
  const color  = node.is_leader ? GREEN : alive ? BLUE : RED;
  const label  = node.is_leader ? "LEADER" : alive ? "STANDBY" : "OFFLINE";

  return (
    <View style={[nr.row, { borderColor: colors.border }]}>
      <View style={[nr.dot, { backgroundColor: color }]} />
      <View style={{ flex: 1 }}>
        <Text style={[nr.host, { color: colors.foreground }]}>
          {node.hostname} <Text style={[nr.id, { color: colors.mutedForeground }]}>({node.node_id})</Text>
        </Text>
        <Text style={[nr.age, { color: colors.mutedForeground }]}>
          آخر نبضة: {alive ? `${node.age_seconds}s` : "منقطع"}
        </Text>
      </View>
      <View style={[nr.badge, { backgroundColor: color + "20", borderColor: color }]}>
        <Text style={[nr.badgeTxt, { color }]}>{label}</Text>
      </View>
    </View>
  );
}

const nr = StyleSheet.create({
  row:      { flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 10, borderBottomWidth: 1 },
  dot:      { width: 8, height: 8, borderRadius: 4 },
  host:     { fontSize: 13, fontWeight: "600" },
  id:       { fontSize: 10 },
  age:      { fontSize: 10, marginTop: 2 },
  badge:    { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, borderWidth: 1 },
  badgeTxt: { fontSize: 10, fontWeight: "700" },
});

// ─── Free Hosting Info ────────────────────────────────────────────────────────

const FREE_HOSTS = [
  { name: "Render",  free: "750 ساعة/شهر • ينام بعد 15d (محلول بالـ ping)", icon: "⚡", color: "#7C3AED" },
  { name: "Railway", free: "$5 رصيد مجاني/شهر • لا ينام • موصى به", icon: "🚂", color: GREEN },
  { name: "Fly.io",  free: "3 VM مجانية • دائمة • ممتازة للـ HA", icon: "✈️", color: BLUE },
  { name: "Koyeb",   free: "Instance واحد مجاني دائماً • 512MB", icon: "🌊", color: "#06B6D4" },
  { name: "Vercel",  free: "❌ لا يدعم FastAPI (serverless فقط)", icon: "▲", color: "#666" },
];

// ─── Main Screen ──────────────────────────────────────────────────────────────

export default function AccountsScreen() {
  const colors  = useColors();
  const insets  = useSafeAreaInsets();

  const [accounts,    setAccounts]    = useState<ExchangeAccount[]>([]);
  const [nodes,       setNodes]       = useState<ServerNode[]>([]);
  const [thisNode,    setThisNode]    = useState<any>(null);
  const [totalBal,    setTotalBal]    = useState(0);
  const [loading,     setLoading]     = useState(false);
  const [refreshing,  setRefreshing]  = useState(false);
  const [showAdd,     setShowAdd]     = useState(false);
  const [balLoading,  setBalLoading]  = useState(false);

  const fetchAll = useCallback(async () => {
    try {
      const [accRes, nodesRes] = await Promise.all([
        fetch(`${getApiBase()}/accounts`, { signal: AbortSignal.timeout(8000) }),
        fetch(`${getApiBase()}/nodes`,    { signal: AbortSignal.timeout(8000) }),
      ]);
      const accD   = await safeJson(accRes);
      const nodesD = await safeJson(nodesRes);

      if (accD?.accounts) setAccounts(accD.accounts);
      if (nodesD?.nodes)  { setNodes(nodesD.nodes); setThisNode(nodesD.this_node); }
    } catch {}
  }, []);

  const fetchBalances = useCallback(async () => {
    setBalLoading(true);
    try {
      const r = await fetch(`${getApiBase()}/accounts/balances`, { signal: AbortSignal.timeout(15000) });
      const d = await safeJson(r);
      if (d?.accounts) {
        const map: Record<string, number> = {};
        for (const b of d.accounts) {
          if (b.account_id) map[b.account_id] = b.total ?? 0;
        }
        setAccounts(prev => prev.map(a => ({
          ...a,
          live_balance: map[a.id] ?? a.live_balance,
        })));
        setTotalBal(d.total_combined_usdt ?? 0);
      }
    } catch {}
    setBalLoading(false);
  }, []);

  useEffect(() => {
    setLoading(true);
    fetchAll().finally(() => setLoading(false));
    const iv = setInterval(() => { fetchAll(); }, 30000);
    return () => clearInterval(iv);
  }, [fetchAll]);

  const onRefresh = async () => {
    setRefreshing(true);
    await fetchAll();
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
      `هل تريد حذف "${name}"؟ لا يمكن التراجع.`,
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

  const activeCount  = accounts.filter(a => a.is_active).length;
  const aliveNodes   = nodes.filter(n => n.alive).length;
  const leaderNode   = nodes.find(n => n.is_leader && n.alive);
  const isThisLeader = thisNode?.is_leader;

  return (
    <View style={[s.root, { backgroundColor: colors.background }]}>
      {/* ── Header ── */}
      <View style={[s.header, { paddingTop: insets.top + 12, borderBottomColor: colors.border }]}>
        <Text style={[s.title, { color: colors.foreground }]}>🏦 ACCOUNTS & CLUSTER</Text>
        <Text style={[s.sub, { color: colors.mutedForeground }]}>Multi-Account + Multi-Server HA</Text>
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
            <Text style={[s.statVal, { color: GREEN }]}>{accounts.length}</Text>
            <Text style={[s.statLbl, { color: colors.mutedForeground }]}>إجمالي الحسابات</Text>
          </View>
          <View style={[s.statCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
            <Text style={[s.statVal, { color: activeCount > 0 ? GREEN : RED }]}>{activeCount}</Text>
            <Text style={[s.statLbl, { color: colors.mutedForeground }]}>مفعّل</Text>
          </View>
          <View style={[s.statCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
            <Text style={[s.statVal, { color: aliveNodes > 1 ? GREEN : YELLOW }]}>{aliveNodes}</Text>
            <Text style={[s.statLbl, { color: colors.mutedForeground }]}>سيرفر نشط</Text>
          </View>
        </View>

        {/* ── Combined Balance ── */}
        {totalBal > 0 && (
          <View style={[s.balCard, { backgroundColor: GREEN + "15", borderColor: GREEN + "40" }]}>
            <Text style={[s.balTitle, { color: colors.mutedForeground }]}>إجمالي رصيد الحسابات الثانوية</Text>
            <Text style={[s.balValue, { color: GREEN }]}>
              ${totalBal.toLocaleString("en-US", { minimumFractionDigits: 2 })} USDT
            </Text>
          </View>
        )}

        {/* ── Exchange Accounts ── */}
        <View style={s.section}>
          <View style={s.sectionHeader}>
            <Text style={[s.sectionTitle, { color: colors.mutedForeground }]}>🏦 حسابات البورصات</Text>
            <View style={{ flexDirection: "row", gap: 8 }}>
              <Pressable
                style={[s.smallBtn, { borderColor: BLUE, opacity: balLoading ? 0.6 : 1 }]}
                onPress={fetchBalances}
                disabled={balLoading}
              >
                {balLoading
                  ? <ActivityIndicator size="small" color={BLUE} />
                  : <Feather name="refresh-cw" size={13} color={BLUE} />
                }
                <Text style={[s.smallBtnTxt, { color: BLUE }]}>أرصدة</Text>
              </Pressable>
              <Pressable
                style={[s.smallBtn, { borderColor: GREEN }]}
                onPress={() => setShowAdd(true)}
              >
                <Feather name="plus" size={13} color={GREEN} />
                <Text style={[s.smallBtnTxt, { color: GREEN }]}>إضافة</Text>
              </Pressable>
            </View>
          </View>

          {loading ? (
            <ActivityIndicator color={GREEN} style={{ marginVertical: 20 }} />
          ) : accounts.length === 0 ? (
            <View style={[s.emptyBox, { backgroundColor: colors.card, borderColor: colors.border }]}>
              <Text style={{ fontSize: 32, marginBottom: 8 }}>🏦</Text>
              <Text style={[s.emptyTitle, { color: colors.foreground }]}>لا توجد حسابات بعد</Text>
              <Text style={[s.emptySub, { color: colors.mutedForeground }]}>
                أضف حساب Bybit أو MEXC ثانٍ لتوزيع التداولات تلقائياً على كل الحسابات
              </Text>
              <Pressable style={[s.emptyBtn, { backgroundColor: GREEN }]} onPress={() => setShowAdd(true)}>
                <Text style={{ color: "#000", fontWeight: "700" }}>➕ أضف أول حساب</Text>
              </Pressable>
            </View>
          ) : (
            accounts.map(acc => (
              <AccountCard
                key={acc.id}
                account={acc}
                onToggle={handleToggle}
                onDelete={handleDelete}
                onRefreshBalance={fetchBalances}
              />
            ))
          )}
        </View>

        {/* ── How it works ── */}
        <View style={[s.infoCard, { backgroundColor: GREEN + "0D", borderColor: GREEN + "30" }]}>
          <Text style={[s.infoTitle, { color: GREEN }]}>⚡ كيف يعمل التداول متعدد الحسابات</Text>
          <Text style={[s.infoText, { color: colors.mutedForeground }]}>
            عند اتخاذ البوت قرار شراء بناءً على الذكاء الاصطناعي، يُنفّذ نفس الأمر تلقائياً على جميع الحسابات الفعّالة في نفس اللحظة — حلال ✓ Spot فقط.
          </Text>
        </View>

        {/* ── Server Cluster ── */}
        <View style={s.section}>
          <View style={s.sectionHeader}>
            <Text style={[s.sectionTitle, { color: colors.mutedForeground }]}>🖥 مجموعة السيرفرات</Text>
            {isThisLeader !== undefined && (
              <View style={[s.leaderBadge, { backgroundColor: isThisLeader ? GREEN + "20" : BLUE + "20", borderColor: isThisLeader ? GREEN : BLUE }]}>
                <Text style={{ color: isThisLeader ? GREEN : BLUE, fontSize: 10, fontWeight: "700" }}>
                  {isThisLeader ? "⭐ هذا القائد" : "👁 احتياطي"}
                </Text>
              </View>
            )}
          </View>

          {nodes.length === 0 ? (
            <View style={[s.emptyBox, { backgroundColor: colors.card, borderColor: colors.border }]}>
              <Text style={[s.emptySub, { color: colors.mutedForeground }]}>
                انشر البوت على Render + Railway + Fly.io وستظهر هنا تلقائياً مع قيادة تلقائية 24/7
              </Text>
            </View>
          ) : (
            <View style={[s.clusterCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
              {nodes.map(node => <NodeRow key={node.node_id} node={node} />)}
            </View>
          )}
        </View>

        {/* ── Free Hosting ── */}
        <View style={s.section}>
          <Text style={[s.sectionTitle, { color: colors.mutedForeground }]}>🆓 خيارات الاستضافة المجانية</Text>
          {FREE_HOSTS.map(h => (
            <View key={h.name} style={[s.hostRow, { backgroundColor: colors.card, borderColor: colors.border }]}>
              <Text style={{ fontSize: 20 }}>{h.icon}</Text>
              <View style={{ flex: 1 }}>
                <Text style={[s.hostName, { color: h.color }]}>{h.name}</Text>
                <Text style={[s.hostFree, { color: colors.mutedForeground }]}>{h.free}</Text>
              </View>
            </View>
          ))}

          <View style={[s.infoCard, { backgroundColor: YELLOW + "10", borderColor: YELLOW + "30", marginTop: 12 }]}>
            <Text style={[s.infoTitle, { color: YELLOW }]}>💡 نصيحة: أقوى إعداد مجاني</Text>
            <Text style={[s.infoText, { color: colors.mutedForeground }]}>
              🚂 Railway (قائد) + ✈️ Fly.io (احتياطي) + ⚡ Render (احتياطي){"\n"}
              عند سقوط القائد، يستلم الاحتياطي خلال 75 ثانية تلقائياً — بدون أي تدخل منك.
            </Text>
          </View>
        </View>
      </ScrollView>

      <AddAccountModal
        visible={showAdd}
        onClose={() => setShowAdd(false)}
        onAdded={fetchAll}
      />
    </View>
  );
}

const s = StyleSheet.create({
  root:          { flex: 1 },
  header:        { paddingHorizontal: 20, paddingBottom: 14, borderBottomWidth: 1 },
  title:         { fontSize: 18, fontWeight: "800", letterSpacing: 1 },
  sub:           { fontSize: 11, marginTop: 2, letterSpacing: 0.5 },
  statsRow:      { flexDirection: "row", gap: 10, marginBottom: 16 },
  statCard:      { flex: 1, borderRadius: 12, borderWidth: 1, padding: 12, alignItems: "center" },
  statVal:       { fontSize: 22, fontWeight: "800" },
  statLbl:       { fontSize: 9, fontWeight: "600", letterSpacing: 0.5, marginTop: 2, textAlign: "center" },
  balCard:       { borderRadius: 12, borderWidth: 1, padding: 14, marginBottom: 16, alignItems: "center" },
  balTitle:      { fontSize: 11, fontWeight: "600", letterSpacing: 0.5, marginBottom: 4 },
  balValue:      { fontSize: 24, fontWeight: "800" },
  section:       { marginBottom: 24 },
  sectionHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 12 },
  sectionTitle:  { fontSize: 11, fontWeight: "700", letterSpacing: 1 },
  smallBtn:      { flexDirection: "row", alignItems: "center", gap: 5, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, borderWidth: 1 },
  smallBtnTxt:   { fontSize: 11, fontWeight: "700" },
  emptyBox:      { borderRadius: 14, borderWidth: 1, padding: 24, alignItems: "center" },
  emptyTitle:    { fontSize: 16, fontWeight: "700", marginBottom: 6 },
  emptySub:      { fontSize: 12, textAlign: "center", lineHeight: 18, marginBottom: 16 },
  emptyBtn:      { paddingHorizontal: 20, paddingVertical: 10, borderRadius: 10 },
  infoCard:      { borderRadius: 12, borderWidth: 1, padding: 14, marginBottom: 8 },
  infoTitle:     { fontSize: 12, fontWeight: "700", marginBottom: 6 },
  infoText:      { fontSize: 12, lineHeight: 18 },
  clusterCard:   { borderRadius: 14, borderWidth: 1, paddingHorizontal: 14 },
  leaderBadge:   { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, borderWidth: 1 },
  hostRow:       { flexDirection: "row", alignItems: "center", gap: 12, padding: 12, borderRadius: 10, borderWidth: 1, marginBottom: 8 },
  hostName:      { fontSize: 13, fontWeight: "700" },
  hostFree:      { fontSize: 11, marginTop: 2 },
});
