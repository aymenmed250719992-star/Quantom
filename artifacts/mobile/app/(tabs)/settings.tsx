import { Feather } from "@expo/vector-icons";
import AsyncStorage from "@react-native-async-storage/async-storage";
import * as Haptics from "expo-haptics";
import { router } from "expo-router";
import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Animated,
  Linking,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { SliderInput } from "@/components/SliderInput";
import {
  getApiBase,
  getServerDomain,
  hasDomain,
  saveServerDomain,
  resetServerDomain,
  fetchRenderDomain,
  DEFAULT_SERVER_DOMAIN,
  safeJson,
} from "@/constants/api";
import { useBotContext } from "@/context/BotContext";
import { useNotify } from "@/context/NotificationContext";
import { useColors } from "@/hooks/useColors";

// ─── Small reusable helpers ───────────────────────────────────────────────────

function SectionHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  const colors = useColors();
  return (
    <View style={{ marginHorizontal: 16, marginBottom: 10 }}>
      <Text style={[sh.title, { color: colors.mutedForeground }]}>{title}</Text>
      {subtitle ? <Text style={[sh.sub, { color: colors.mutedForeground }]}>{subtitle}</Text> : null}
    </View>
  );
}
const sh = StyleSheet.create({
  title: { fontSize: 11, fontWeight: "700", letterSpacing: 1 },
  sub:   { fontSize: 10, marginTop: 2, lineHeight: 15 },
});

// ─── Server URL section ───────────────────────────────────────────────────────

function ServerUrlSection() {
  const colors  = useColors();
  const [url,       setUrl]       = useState(getServerDomain());
  const [saving,    setSaving]    = useState(false);
  const [testing,   setTesting]   = useState(false);
  const [detecting, setDetecting] = useState(false);
  const [msg,       setMsg]       = useState("");

  const showMsg = (m: string) => { setMsg(m); setTimeout(() => setMsg(""), 4000); };

  const handleSave = async () => {
    const clean = url.trim().replace(/^https?:\/\//, "").replace(/\/+$/, "");
    if (!clean) { showMsg("❌ أدخل عنوان الخادم"); return; }
    setSaving(true);
    await saveServerDomain(clean);
    setUrl(clean);
    showMsg("✅ تم الحفظ — أعد تشغيل التطبيق لتفعيل التغيير");
    setSaving(false);
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
  };

  const handleTest = async () => {
    setTesting(true); setMsg("⏳ جارٍ اختبار الاتصال...");
    try {
      const ctrl = new AbortController();
      const _t = setTimeout(() => ctrl.abort(), 8000);
      const r = await fetch(`https://${url.replace(/^https?:\/\//, "")}/trade/health`, { signal: ctrl.signal });
      clearTimeout(_t);
      const d = await safeJson(r);
      showMsg(d && d.health_score !== undefined
        ? `✅ متصل — صحة النظام: ${d.health_score}%`
        : "✅ الخادم يرد");
    } catch (e: any) {
      showMsg(`❌ تعذّر الاتصال — ${e.message?.slice(0, 60) ?? "خطأ"}`);
    }
    setTesting(false);
  };

  const handleAutoDetect = async () => {
    setDetecting(true);
    showMsg("⏳ أبحث عن رابط السيرفر...");
    const domain = await fetchRenderDomain();
    if (domain) {
      setUrl(domain);
      await saveServerDomain(domain);
      showMsg(`✅ تم الكشف تلقائياً: ${domain}`);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    } else {
      showMsg("ℹ️ لم يُعثر على السيرفر تلقائياً — أدخل الرابط يدوياً");
    }
    setDetecting(false);
  };

  const handleReset = () => {
    setUrl(DEFAULT_SERVER_DOMAIN);
    resetServerDomain();
    showMsg("↩ تم الإعادة للقيمة الافتراضية");
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
  };

  const isDefault = url.trim().replace(/^https?:\/\//, "") === DEFAULT_SERVER_DOMAIN;

  return (
    <View style={su.wrap}>

      {/* ── No-domain setup banner (shown when APK launched with no server URL) ── */}
      {!hasDomain() && (
        <View style={[su.noDomainBanner, { backgroundColor: "#EF444415", borderColor: "#EF444440" }]}>
          <Feather name="alert-triangle" size={14} color="#EF4444" />
          <View style={{ flex: 1 }}>
            <Text style={[su.noDomainTitle, { color: "#EF4444" }]}>رابط السيرفر غير محدد</Text>
            <Text style={[su.noDomainSub, { color: "#EF444499" }]}>
              أدخل عنوان السيرفر أدناه واضغط «حفظ الرابط» لتفعيل البوت
            </Text>
          </View>
        </View>
      )}

      {/* ── Current URL display ── */}
      <View style={[su.currentBox, { backgroundColor: colors.muted, borderColor: colors.border }]}>
        <Feather name="server" size={13} color={colors.mutedForeground} />
        <Text style={[su.currentTxt, { color: colors.mutedForeground }]} numberOfLines={1}>
          {hasDomain() ? getApiBase() : "—"}
        </Text>
      </View>

      {/* ── Input ── */}
      <View style={[su.inputWrap, { borderColor: colors.border, backgroundColor: colors.card }]}>
        <Text style={[su.proto, { color: colors.mutedForeground }]}>https://</Text>
        <TextInput
          style={[su.input, { color: colors.foreground }]}
          value={url.replace(/^https?:\/\//, "")}
          onChangeText={v => setUrl(v)}
          placeholder="my-bot.onrender.com"
          placeholderTextColor={colors.mutedForeground}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
        />
      </View>

      {/* ── Auto-detect Render button ── */}
      <Pressable
        style={[su.detectBtn, { borderColor: "#F59E0B", opacity: detecting ? 0.6 : 1 }]}
        onPress={handleAutoDetect}
        disabled={detecting || saving || testing}
      >
        {detecting
          ? <ActivityIndicator size="small" color="#F59E0B" />
          : <Feather name="zap" size={13} color="#F59E0B" />
        }
        <Text style={[su.testBtnTxt, { color: "#F59E0B" }]}>
          {detecting ? "جارٍ الكشف..." : "كشف Render تلقائياً"}
        </Text>
      </Pressable>

      {/* ── Buttons row ── */}
      <View style={{ flexDirection: "row", gap: 8 }}>
        <Pressable
          style={[su.testBtn, { borderColor: "#22C55E", opacity: testing ? 0.6 : 1 }]}
          onPress={handleTest}
          disabled={testing || saving || detecting}
        >
          {testing
            ? <ActivityIndicator size="small" color="#22C55E" />
            : <Feather name="wifi" size={13} color="#22C55E" />
          }
          <Text style={[su.testBtnTxt, { color: "#22C55E" }]}>اختبار</Text>
        </Pressable>

        {!isDefault && (
          <Pressable style={[su.resetBtn, { borderColor: colors.border }]} onPress={handleReset}>
            <Feather name="rotate-ccw" size={13} color={colors.mutedForeground} />
          </Pressable>
        )}

        <Pressable
          style={[su.saveBtn, { backgroundColor: saving ? colors.muted : "#3B82F6", flex: 1, opacity: saving ? 0.7 : 1 }]}
          onPress={handleSave}
          disabled={saving || testing || detecting}
        >
          {saving
            ? <ActivityIndicator size="small" color="#fff" />
            : <Feather name="save" size={13} color="#fff" />
          }
          <Text style={su.saveBtnTxt}>{saving ? "جارٍ الحفظ..." : "حفظ الرابط"}</Text>
        </Pressable>
      </View>

      {msg ? (
        <Text style={[su.msg, {
          color: msg.startsWith("✅") ? "#22C55E" : msg.startsWith("⏳") ? colors.mutedForeground : msg.startsWith("↩") ? colors.mutedForeground : "#EF4444",
        }]}>
          {msg}
        </Text>
      ) : null}

      {/* ── Help hint ── */}
      <View style={[su.hint, { backgroundColor: "#3B82F608", borderColor: "#3B82F622" }]}>
        <Feather name="info" size={11} color="#3B82F6" />
        <Text style={[su.hintTxt, { color: "#3B82F6" }]}>
          رابط السيرفر الحالي:{"\n"}
          <Text style={{ fontFamily: Platform.OS === "ios" ? "Courier New" : "monospace", fontSize: 10 }}>
            {getServerDomain()}
          </Text>
        </Text>
      </View>
    </View>
  );
}

const su = StyleSheet.create({
  wrap:           { gap: 10 },
  noDomainBanner: { flexDirection: "row", alignItems: "flex-start", gap: 10, padding: 12, borderRadius: 11, borderWidth: 1.5 },
  noDomainTitle:  { fontSize: 13, fontWeight: "700" },
  noDomainSub:    { fontSize: 11, marginTop: 2, lineHeight: 16 },
  currentBox:  { flexDirection: "row", alignItems: "center", gap: 8, padding: 10, borderRadius: 10, borderWidth: 1 },
  currentTxt:  { flex: 1, fontSize: 11, fontFamily: Platform.OS === "ios" ? "Courier New" : "monospace" },
  inputWrap:   { flexDirection: "row", alignItems: "center", borderRadius: 11, borderWidth: 1.5, paddingLeft: 10, paddingRight: 4 },
  proto:       { fontSize: 12, fontWeight: "600" },
  input:       { flex: 1, height: 46, fontSize: 12, fontFamily: Platform.OS === "ios" ? "Courier New" : "monospace" },
  detectBtn:   { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, height: 44, borderRadius: 11, borderWidth: 1.5, paddingHorizontal: 14 },
  testBtn:     { flexDirection: "row", alignItems: "center", gap: 6, height: 44, borderRadius: 11, borderWidth: 1.5, paddingHorizontal: 14 },
  testBtnTxt:  { fontSize: 12, fontWeight: "700" },
  resetBtn:    { alignItems: "center", justifyContent: "center", width: 44, height: 44, borderRadius: 11, borderWidth: 1.5 },
  saveBtn:     { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 7, height: 44, borderRadius: 11 },
  saveBtnTxt:  { fontSize: 13, fontWeight: "700", color: "#fff" },
  msg:         { fontSize: 11, fontWeight: "600", lineHeight: 16 },
  hint:        { flexDirection: "row", gap: 7, padding: 10, borderRadius: 9, borderWidth: 1, alignItems: "flex-start" },
  hintTxt:     { flex: 1, fontSize: 11, lineHeight: 16 },
});


function InfoBox({ icon, text, color }: { icon: string; text: string; color: string }) {
  return (
    <View style={[ib.wrap, { backgroundColor: `${color}0F`, borderColor: `${color}22` }]}>
      <Feather name={icon as any} size={12} color={color} />
      <Text style={[ib.txt, { color }]}>{text}</Text>
    </View>
  );
}
const ib = StyleSheet.create({
  wrap: { flexDirection: "row", gap: 8, padding: 12, borderRadius: 10, borderWidth: 1, alignItems: "flex-start", marginTop: 8 },
  txt:  { flex: 1, fontSize: 12, lineHeight: 17 },
});

// ─── AI Provider section ──────────────────────────────────────────────────────

type ProviderId = "gemini" | "openai" | "claude" | "groq" | "grok" | "custom";

const AI_PROVIDERS: {
  id: ProviderId; label: string; color: string; icon: string;
  hint: string; hintUrl?: string; defaultModel?: string; needsBaseUrl?: boolean; free?: boolean; badge?: string;
}[] = [
  {
    id: "gemini",  label: "Gemini",  color: "#4285F4", icon: "zap",
    hint: "aistudio.google.com/app/apikey",
    hintUrl: "https://aistudio.google.com/app/apikey",
    defaultModel: "gemini-2.5-flash",
    free: true, badge: "مجاني",
  },
  {
    id: "groq",    label: "Groq",    color: "#F55036", icon: "cpu",
    hint: "console.groq.com — llama-3.3-70b-versatile",
    hintUrl: "https://console.groq.com",
    defaultModel: "llama-3.3-70b-versatile",
    free: true, badge: "مجاني 100%",
  },
  {
    id: "openai",  label: "OpenAI",  color: "#10A37F", icon: "message-circle",
    hint: "platform.openai.com/api-keys",
    hintUrl: "https://platform.openai.com/api-keys",
    defaultModel: "gpt-4o-mini",
  },
  {
    id: "claude",  label: "Claude",  color: "#D97706", icon: "feather",
    hint: "console.anthropic.com/settings/keys",
    hintUrl: "https://console.anthropic.com/settings/keys",
    defaultModel: "claude-3-5-haiku-20241022",
  },
  {
    id: "grok",    label: "Grok",    color: "#6366F1", icon: "activity",
    hint: "console.x.ai — مفتاح Grok API",
    hintUrl: "https://console.x.ai",
    defaultModel: "grok-3-mini",
  },
  {
    id: "custom",  label: "Custom",  color: "#7C3AED", icon: "settings",
    hint: "أي API متوافق مع OpenAI",
    needsBaseUrl: true, defaultModel: "gpt-4o-mini",
  },
];

// ── Quick-fill presets for Custom provider ────────────────────────────────────
interface Preset { label: string; color: string; base_url: string; model: string; name: string; free?: boolean }
const CUSTOM_PRESETS: Preset[] = [
  { label: "Groq",       color: "#F55036", name: "Groq",        base_url: "https://api.groq.com/openai/v1",           model: "llama-3.3-70b-versatile",   free: true  },
  { label: "Together",   color: "#0066FF", name: "Together AI", base_url: "https://api.together.xyz/v1",              model: "meta-llama/Llama-3-70b-chat-hf"              },
  { label: "OpenRouter", color: "#6D28D9", name: "OpenRouter",  base_url: "https://openrouter.ai/api/v1",             model: "openai/gpt-4o-mini"                          },
  { label: "Ollama",     color: "#1E7F5E", name: "Ollama",      base_url: "http://localhost:11434/v1",                model: "llama3.2",                  free: true  },
  { label: "Mistral",    color: "#FF7000", name: "Mistral AI",  base_url: "https://api.mistral.ai/v1",               model: "mistral-small-latest"                        },
];

function AIProviderSection() {
  const colors = useColors();
  const [poolStatus, setPoolStatus] = useState<{
    active_provider: string | null; available_keys: number; total_keys: number; keys: any[];
  } | null>(null);
  const [selectedProvider, setSelectedProvider] = useState<ProviderId>("gemini");
  const [apiKey,       setApiKey]       = useState("");
  const [baseUrl,      setBaseUrl]      = useState("");
  const [modelName,    setModelName]    = useState("");
  const [customLabel,  setCustomLabel]  = useState("");
  const [showKey,      setShowKey]      = useState(false);
  const [saving,       setSaving]       = useState(false);
  const [testing,      setTesting]      = useState(false);
  const [resetMsg,     setResetMsg]     = useState("");
  const [saveMsg,      setSaveMsg]      = useState("");
  const [activePreset, setActivePreset] = useState<string>("");

  const load = useCallback(async () => {
    try {
      const r = await fetch(`${getApiBase()}/ai/providers`);
      const d = await safeJson(r);
      if (d) setPoolStatus(d);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Reset extra fields when provider changes
  useEffect(() => {
    const p = AI_PROVIDERS.find(x => x.id === selectedProvider)!;
    setModelName(p.defaultModel ?? "");
    setBaseUrl("");
    setCustomLabel("");
    setActivePreset("");
    setSaveMsg("");
  }, [selectedProvider]);

  const applyPreset = (preset: Preset) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setCustomLabel(preset.name);
    setBaseUrl(preset.base_url);
    setModelName(preset.model);
    setActivePreset(preset.label);
  };

  const handleSave = async () => {
    if (!apiKey.trim()) { setSaveMsg("❌ أدخل مفتاح API أولاً"); return; }
    const p = AI_PROVIDERS.find(x => x.id === selectedProvider)!;
    if (p.needsBaseUrl && !baseUrl.trim()) { setSaveMsg("❌ أدخل Base URL للمزود المخصص"); return; }
    setSaving(true); setSaveMsg("");
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    try {
      const body: any = {
        provider:   selectedProvider,
        api_key:    apiKey.trim(),
        model_name: modelName.trim() || p.defaultModel,
      };
      if (baseUrl.trim())     body.base_url      = baseUrl.trim();
      if (customLabel.trim()) body.display_label = customLabel.trim();

      const r = await fetch(`${getApiBase()}/ai/key`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const d = await safeJson(r);
      if (!d) { setSaveMsg("❌ لا يمكن الوصول للسيرفر — تحقق من الاتصال"); }
      else if (d.success) {
        setSaveMsg(`✅ تم إضافة ${d.label} بنجاح`);
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        setApiKey(""); setBaseUrl(""); setCustomLabel(""); setActivePreset("");
        await load();
      } else {
        setSaveMsg(`❌ ${d.error || "حدث خطأ في الإضافة"}`);
      }
    } catch (e: any) {
      setSaveMsg(`❌ تعذّر الاتصال: ${e.message}`);
    }
    setSaving(false);
  };

  const handleTest = async () => {
    if (!apiKey.trim()) { setSaveMsg("❌ أدخل مفتاح API أولاً"); return; }
    setTesting(true); setSaveMsg("⏳ جارٍ اختبار المفتاح...");
    try {
      const body: any = {
        provider:   selectedProvider,
        api_key:    apiKey.trim(),
        model_name: modelName.trim() || AI_PROVIDERS.find(x => x.id === selectedProvider)?.defaultModel,
        test_only:  true,
      };
      const r = await fetch(`${getApiBase()}/ai/key`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const d = await safeJson(r);
      setSaveMsg(!d ? "❌ لا يمكن الوصول للسيرفر" : d.success ? `✅ المفتاح يعمل — ${d.label}` : `❌ ${d.error || "المفتاح غير صالح"}`);
    } catch (e: any) {
      setSaveMsg(`❌ تعذّر الاتصال`);
    }
    setTesting(false);
  };

  const handleReset = async () => {
    setResetMsg("");
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    try {
      const r = await fetch(`${getApiBase()}/ai/reset`, { method: "POST" });
      const d = await safeJson(r);
      setResetMsg(!d ? "❌ لا يمكن الوصول للسيرفر" : d.success ? "✅ تم إعادة تشغيل AI" : "❌ فشل");
      await load();
    } catch { setResetMsg("❌ تعذّر الاتصال"); }
    setTimeout(() => setResetMsg(""), 3000);
  };

  const handleDeleteKey = async (provider: string, label: string) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    try {
      const params = new URLSearchParams({ provider, label });
      const r = await fetch(`${getApiBase()}/ai/key?${params}`, { method: "DELETE" });
      const d = await safeJson(r);
      if (d?.success) {
        setSaveMsg(`🗑️ تم حذف ${label}`);
        await load();
      } else {
        setSaveMsg("❌ تعذّر الحذف");
      }
    } catch { setSaveMsg("❌ تعذّر الاتصال"); }
    setTimeout(() => setSaveMsg(""), 3000);
  };

  const activeKey    = poolStatus?.keys?.find((k: any) => k.available);
  const activePInfo  = AI_PROVIDERS.find(p => p.id === (activeKey?.provider ?? poolStatus?.active_provider ?? ""));
  const hasKeys      = (poolStatus?.total_keys ?? 0) > 0;
  const selP         = AI_PROVIDERS.find(x => x.id === selectedProvider)!;

  // Providers in 3-col grid (row1: Gemini/Groq/OpenAI, row2: Claude/Grok/Custom)
  const row1 = AI_PROVIDERS.slice(0, 3);
  const row2 = AI_PROVIDERS.slice(3);

  return (
    <View style={ap.wrap}>

      {/* ── Status bar ── */}
      <View style={[ap.statusBar, {
        backgroundColor: hasKeys ? `${activePInfo?.color ?? colors.primary}10` : `${colors.mutedForeground}0C`,
        borderColor:     hasKeys ? `${activePInfo?.color ?? colors.primary}33` : colors.border,
      }]}>
        <View style={[ap.statusDot, { backgroundColor: hasKeys ? (activePInfo?.color ?? colors.primary) : colors.mutedForeground }]} />
        <View style={{ flex: 1 }}>
          <Text style={[ap.statusTitle, { color: colors.foreground }]}>
            {hasKeys ? `${poolStatus?.available_keys}/${poolStatus?.total_keys} مزود نشط` : "لا يوجد AI Provider"}
          </Text>
          <Text style={[ap.statusSub, { color: colors.mutedForeground }]}>
            {hasKeys
              ? `Quantom V2 Core — ${poolStatus?.total_keys} مفتاح مضاف`
              : "أضف مفتاح API لتفعيل Quantom V2 Core"}
          </Text>
        </View>
        <Pressable style={[ap.resetBtn, { borderColor: `${colors.mutedForeground}44` }]} onPress={load}>
          <Feather name="refresh-cw" size={12} color={colors.mutedForeground} />
        </Pressable>
      </View>

      {/* ── First-time Setup Wizard (only when no keys) ── */}
      {!hasKeys && (
        <View style={ap.wizardCard}>
          <View style={ap.wizardHeader}>
            <View style={ap.wizardIconWrap}>
              <Feather name="zap" size={18} color="#4285F4" />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={ap.wizardTitle}>ابدأ في 3 خطوات — مجاناً تماماً</Text>
              <Text style={ap.wizardSub}>Gemini من Google مجاني 100% • لا بطاقة ائتمانية</Text>
            </View>
          </View>

          {/* Steps */}
          {[
            { n: "١", icon: "globe" as const,      color: "#4285F4", text: 'افتح الرابط أدناه وسجّل بحساب Google' },
            { n: "٢", icon: "copy" as const,       color: "#34A853", text: 'اضغط "Create API key" ثم انسخ المفتاح' },
            { n: "٣", icon: "check-circle" as const, color: "#A78BFA", text: 'اختر Gemini أدناه، الصق المفتاح واضغط إضافة' },
          ].map(step => (
            <View key={step.n} style={ap.wizardStep}>
              <View style={[ap.wizardStepNum, { backgroundColor: `${step.color}20` }]}>
                <Text style={[ap.wizardStepNumTxt, { color: step.color }]}>{step.n}</Text>
              </View>
              <Feather name={step.icon} size={13} color={step.color} style={{ marginTop: 1 }} />
              <Text style={ap.wizardStepTxt}>{step.text}</Text>
            </View>
          ))}

          {/* CTA buttons */}
          <View style={{ gap: 8, marginTop: 4 }}>
            <Pressable
              style={[ap.wizardBtn, { backgroundColor: "#4285F4" }]}
              onPress={() => {
                Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
                Linking.openURL("https://aistudio.google.com/app/apikey");
              }}
            >
              <Feather name="external-link" size={14} color="#fff" />
              <Text style={ap.wizardBtnTxt}>فتح Google AI Studio — احصل على مفتاح مجاني</Text>
            </Pressable>

            <Pressable
              style={[ap.wizardBtn, { backgroundColor: "#F5503620" , borderWidth: 1, borderColor: "#F5503644" }]}
              onPress={() => {
                Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
                Linking.openURL("https://console.groq.com/keys");
              }}
            >
              <Feather name="cpu" size={14} color="#F55036" />
              <Text style={[ap.wizardBtnTxt, { color: "#F55036" }]}>أو احصل على Groq مجاناً (Llama 70B)</Text>
            </Pressable>
          </View>

          <View style={ap.wizardNote}>
            <Feather name="shield" size={10} color="#22C55E" />
            <Text style={ap.wizardNoteTxt}>مفاتيحك محفوظة محلياً داخل السيرفر فقط — لا تُرسل لأي جهة</Text>
          </View>
        </View>
      )}

      {/* ── Stored keys list ── */}
      {hasKeys && (poolStatus?.keys ?? []).map((k: any, i: number) => {
        const pInfo = AI_PROVIDERS.find(p => p.id === k.provider);
        return (
          <View key={`${k.provider}-${i}`} style={[ap.keyRow, {
            borderColor:     k.available ? `${pInfo?.color ?? colors.primary}44` : colors.border,
            backgroundColor: k.available ? `${pInfo?.color ?? colors.primary}08` : colors.muted,
          }]}>
            <View style={[ap.keyDot, { backgroundColor: pInfo?.color ?? (k.available ? colors.primary : colors.mutedForeground) }]} />
            <View style={{ flex: 1 }}>
              <Text style={[ap.keyLabel, { color: colors.foreground }]} numberOfLines={1}>
                {k.label ?? k.provider}
              </Text>
              <Text style={[ap.keySub, { color: colors.mutedForeground }]} numberOfLines={1}>
                {pInfo?.label ?? k.provider} · {k.model ?? ""}
              </Text>
            </View>
            <View style={[ap.keyStatusBadge, {
              backgroundColor: k.available ? `${pInfo?.color ?? colors.primary}20` : `${colors.mutedForeground}20`,
            }]}>
              <Text style={[ap.keyStatus, { color: k.available ? (pInfo?.color ?? colors.primary) : colors.mutedForeground }]}>
                {k.available ? "نشط" : "منتهي"}
              </Text>
            </View>
            <Pressable onPress={() => handleDeleteKey(k.provider, k.label ?? "")} style={ap.keyDelBtn} hitSlop={10}>
              <Feather name="trash-2" size={14} color={colors.destructive} />
            </Pressable>
          </View>
        );
      })}

      {resetMsg ? (
        <Text style={[ap.msg, { color: resetMsg.startsWith("✅") ? colors.primary : colors.destructive }]}>{resetMsg}</Text>
      ) : null}

      {/* ── Divider ── */}
      <View style={[ap.divider, { backgroundColor: colors.border }]} />
      <Text style={[ap.addTitle, { color: colors.mutedForeground }]}>إضافة مفتاح API جديد</Text>

      {/* ── Provider grid row 1 ── */}
      <View style={ap.providerRow}>
        {row1.map(p => {
          const active = selectedProvider === p.id;
          return (
            <Pressable
              key={p.id}
              onPress={() => { setSelectedProvider(p.id); Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light); }}
              style={[ap.providerBtn, {
                backgroundColor: active ? `${p.color}1A` : colors.muted,
                borderColor:     active ? p.color : colors.border,
                borderWidth:     active ? 2 : 1,
              }]}
            >
              <Feather name={p.icon as any} size={14} color={active ? p.color : colors.mutedForeground} />
              <View style={{ alignItems: "center", gap: 2 }}>
                <Text style={[ap.providerBtnTxt, { color: active ? p.color : colors.mutedForeground, fontWeight: active ? "800" : "500" }]}>
                  {p.label}
                </Text>
                {p.free && (
                  <View style={[ap.freeBadgeSmall, { backgroundColor: active ? p.color : "#22C55E" }]}>
                    <Text style={ap.freeBadgeSmallTxt}>FREE</Text>
                  </View>
                )}
              </View>
            </Pressable>
          );
        })}
      </View>

      {/* ── Provider grid row 2 ── */}
      <View style={ap.providerRow}>
        {row2.map(p => {
          const active = selectedProvider === p.id;
          return (
            <Pressable
              key={p.id}
              onPress={() => { setSelectedProvider(p.id); Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light); }}
              style={[ap.providerBtn, {
                backgroundColor: active ? `${p.color}1A` : colors.muted,
                borderColor:     active ? p.color : colors.border,
                borderWidth:     active ? 2 : 1,
              }]}
            >
              <Feather name={p.icon as any} size={14} color={active ? p.color : colors.mutedForeground} />
              <Text style={[ap.providerBtnTxt, { color: active ? p.color : colors.mutedForeground, fontWeight: active ? "800" : "500" }]}>
                {p.label}
              </Text>
            </Pressable>
          );
        })}
      </View>

      {/* ── Hint (where to get key) ── */}
      <View style={[ap.hintBox, { backgroundColor: `${selP.color}0A`, borderColor: `${selP.color}22` }]}>
        <Feather name="info" size={11} color={selP.color} />
        <Text style={[ap.hintTxt, { color: selP.color }]}>
          {selP.badge ? `[${selP.badge}]  ` : ""}{selP.hint}
        </Text>
      </View>

      {/* ── Quick Presets (Custom only) ── */}
      {selectedProvider === "custom" && (
        <View style={[ap.presetsWrap, { borderColor: `${selP.color}33`, backgroundColor: `${selP.color}08` }]}>
          <Text style={[ap.presetsLabel, { color: colors.mutedForeground }]}>⚡ اختر مزوداً جاهزاً</Text>
          <View style={ap.presetsRow}>
            {CUSTOM_PRESETS.map(preset => {
              const isActive = activePreset === preset.label;
              return (
                <Pressable
                  key={preset.label}
                  onPress={() => applyPreset(preset)}
                  style={[ap.presetBtn, {
                    backgroundColor: isActive ? `${preset.color}20` : colors.muted,
                    borderColor:     isActive ? preset.color : colors.border,
                    borderWidth:     isActive ? 2 : 1,
                  }]}
                >
                  <Text style={[ap.presetBtnLabel, { color: isActive ? preset.color : colors.foreground }]}>
                    {preset.label}
                  </Text>
                  {preset.free && (
                    <View style={[ap.freeBadge, { backgroundColor: isActive ? preset.color : "#22C55E" }]}>
                      <Text style={ap.freeBadgeTxt}>FREE</Text>
                    </View>
                  )}
                </Pressable>
              );
            })}
          </View>
          {activePreset ? (
            <Text style={[ap.presetInfo, { color: colors.mutedForeground }]}>
              ✓ {activePreset} · {CUSTOM_PRESETS.find(p => p.label === activePreset)?.model}
            </Text>
          ) : null}
        </View>
      )}

      {/* ── Custom label ── */}
      {selectedProvider === "custom" && (
        <View style={[ap.inputWrap, { borderColor: customLabel ? `${selP.color}88` : colors.border, backgroundColor: colors.card }]}>
          <Feather name="tag" size={14} color={colors.mutedForeground} style={{ marginRight: 8 }} />
          <TextInput
            style={[ap.input, { color: colors.foreground }]}
            value={customLabel}
            onChangeText={setCustomLabel}
            placeholder="اسم المزود (مثال: Groq-Free / Ollama)"
            placeholderTextColor={colors.mutedForeground}
            autoCapitalize="none"
            autoCorrect={false}
          />
        </View>
      )}

      {/* ── Base URL (Custom) ── */}
      {selectedProvider === "custom" && (
        <View style={[ap.inputWrap, { borderColor: baseUrl ? `${selP.color}88` : colors.border, backgroundColor: colors.card }]}>
          <Feather name="link" size={14} color={colors.mutedForeground} style={{ marginRight: 8 }} />
          <TextInput
            style={[ap.input, { color: colors.foreground }]}
            value={baseUrl}
            onChangeText={setBaseUrl}
            placeholder="Base URL  (مثال: https://api.groq.com/openai/v1)"
            placeholderTextColor={colors.mutedForeground}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
          />
        </View>
      )}

      {/* ── Model name (grok / custom) ── */}
      {(selectedProvider === "grok" || selectedProvider === "groq" || selectedProvider === "custom") && (
        <View style={[ap.inputWrap, { borderColor: modelName ? `${selP.color}66` : colors.border, backgroundColor: colors.card }]}>
          <Feather name="cpu" size={14} color={colors.mutedForeground} style={{ marginRight: 8 }} />
          <TextInput
            style={[ap.input, { color: colors.foreground }]}
            value={modelName}
            onChangeText={setModelName}
            placeholder={`Model  (افتراضي: ${selP.defaultModel})`}
            placeholderTextColor={colors.mutedForeground}
            autoCapitalize="none"
            autoCorrect={false}
          />
        </View>
      )}

      {/* ── API Key input ── */}
      <View style={[ap.inputWrap, {
        borderColor:     apiKey ? selP.color : colors.border,
        borderWidth:     apiKey ? 2 : 1.5,
        backgroundColor: colors.card,
      }]}>
        <Feather name="key" size={14} color={apiKey ? selP.color : colors.mutedForeground} style={{ marginRight: 8 }} />
        <TextInput
          style={[ap.input, { color: colors.foreground }]}
          value={apiKey}
          onChangeText={setApiKey}
          placeholder={`${selP.label} API Key — الصق مفتاحك هنا`}
          placeholderTextColor={colors.mutedForeground}
          secureTextEntry={!showKey}
          autoCapitalize="none"
          autoCorrect={false}
        />
        <Pressable style={ap.eye} onPress={() => setShowKey(v => !v)} hitSlop={8}>
          <Feather name={showKey ? "eye-off" : "eye"} size={15} color={colors.mutedForeground} />
        </Pressable>
      </View>

      {/* ── Buttons row ── */}
      <View style={{ flexDirection: "row", gap: 8 }}>
        <Pressable
          style={[ap.testBtn, { borderColor: selP.color, opacity: testing ? 0.6 : 1 }]}
          onPress={handleTest}
          disabled={testing || saving}
        >
          {testing
            ? <ActivityIndicator size="small" color={selP.color} />
            : <Feather name="check-circle" size={14} color={selP.color} />
          }
          <Text style={[ap.testBtnTxt, { color: selP.color }]}>{testing ? "اختبار..." : "اختبار"}</Text>
        </Pressable>

        <Pressable
          style={[ap.saveBtn, { backgroundColor: saving ? colors.muted : selP.color, flex: 1, opacity: saving ? 0.7 : 1 }]}
          onPress={handleSave}
          disabled={saving || testing}
        >
          {saving
            ? <ActivityIndicator size="small" color="#fff" />
            : <Feather name="plus" size={14} color="#fff" />
          }
          <Text style={ap.saveBtnTxt}>{saving ? "جارٍ الإضافة..." : `إضافة ${selP.label}`}</Text>
        </Pressable>
      </View>

      {saveMsg ? (
        <Text style={[ap.msg, { color: saveMsg.startsWith("✅") ? "#22C55E" : saveMsg.startsWith("⏳") ? colors.mutedForeground : colors.destructive }]}>
          {saveMsg}
        </Text>
      ) : null}
    </View>
  );
}

const ap = StyleSheet.create({
  wrap:              { gap: 10 },
  // ── Status bar ──
  statusBar:         { flexDirection: "row", alignItems: "center", gap: 10, padding: 14, borderRadius: 12, borderWidth: 1 },
  statusDot:         { width: 10, height: 10, borderRadius: 5, flexShrink: 0 },
  statusTitle:       { fontSize: 14, fontWeight: "700" },
  statusSub:         { fontSize: 10, marginTop: 2 },
  resetBtn:          { alignItems: "center", justifyContent: "center", width: 30, height: 30, borderRadius: 8, borderWidth: 1 },
  resetBtnTxt:       { fontSize: 10, fontWeight: "600" },
  // ── Key rows ──
  keyRow:            { flexDirection: "row", alignItems: "center", gap: 8, paddingHorizontal: 12, paddingVertical: 10, borderRadius: 12, borderWidth: 1 },
  keyDot:            { width: 9, height: 9, borderRadius: 5, flexShrink: 0 },
  keyLabel:          { fontSize: 13, fontWeight: "700" },
  keySub:            { fontSize: 10, marginTop: 1 },
  keyStatusBadge:    { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 20 },
  keyStatus:         { fontSize: 10, fontWeight: "700" },
  keyDelBtn:         { padding: 5 },
  // ── Divider & section label ──
  divider:           { height: 1, marginVertical: 4 },
  addTitle:          { fontSize: 11, fontWeight: "700", letterSpacing: 0.8, textTransform: "uppercase", marginBottom: 2 },
  // ── Provider grid ──
  providerRow:       { flexDirection: "row", gap: 8 },
  providerBtn:       { flex: 1, flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 5, paddingVertical: 12, borderRadius: 12 },
  providerBtnTxt:    { fontSize: 11 },
  // ── Free badge (inside provider button) ──
  freeBadgeSmall:    { paddingHorizontal: 5, paddingVertical: 1, borderRadius: 4 },
  freeBadgeSmallTxt: { fontSize: 7, fontWeight: "900", color: "#fff", letterSpacing: 0.5 },
  // ── Hint box ──
  hintBox:           { flexDirection: "row", alignItems: "center", gap: 7, padding: 9, borderRadius: 9, borderWidth: 1 },
  hintTxt:           { flex: 1, fontSize: 10, fontWeight: "600", lineHeight: 15 },
  // ── Presets ──
  presetsWrap:       { gap: 8, padding: 12, borderRadius: 12, borderWidth: 1 },
  presetsLabel:      { fontSize: 10, fontWeight: "600", letterSpacing: 0.5, textTransform: "uppercase" },
  presetsRow:        { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  presetBtn:         { flexDirection: "row", alignItems: "center", gap: 5, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 20 },
  presetBtnLabel:    { fontSize: 12, fontWeight: "700" },
  freeBadge:         { paddingHorizontal: 5, paddingVertical: 1, borderRadius: 4 },
  freeBadgeTxt:      { fontSize: 8, fontWeight: "800", color: "#fff", letterSpacing: 0.5 },
  presetInfo:        { fontSize: 10, fontFamily: "monospace", marginTop: 2 },
  // ── Inputs ──
  inputWrap:         { flexDirection: "row", alignItems: "center", borderRadius: 11, borderWidth: 1.5, paddingHorizontal: 12, marginTop: 2 },
  input:             { flex: 1, height: 48, fontSize: 13, fontFamily: Platform.OS === "ios" ? "Courier New" : "monospace" },
  eye:               { padding: 8 },
  // ── Buttons ──
  testBtn:           { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, height: 46, borderRadius: 12, borderWidth: 1.5, paddingHorizontal: 16, marginTop: 4 },
  testBtnTxt:        { fontSize: 13, fontWeight: "700" },
  saveBtn:           { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, height: 46, borderRadius: 12, marginTop: 4 },
  saveBtnTxt:        { fontSize: 14, fontWeight: "700", color: "#fff" },
  msg:               { fontSize: 12, textAlign: "center", marginTop: 6, fontWeight: "600" },
  // ── First-time Setup Wizard ──
  wizardCard:        { backgroundColor: "#4285F408", borderWidth: 1.5, borderColor: "#4285F433", borderRadius: 14, padding: 14, gap: 10 },
  wizardHeader:      { flexDirection: "row", alignItems: "center", gap: 10 },
  wizardIconWrap:    { width: 36, height: 36, borderRadius: 10, backgroundColor: "#4285F415", alignItems: "center", justifyContent: "center" },
  wizardTitle:       { fontSize: 14, fontWeight: "800", color: "#4285F4" },
  wizardSub:         { fontSize: 10, color: "#4285F4AA", marginTop: 2 },
  wizardStep:        { flexDirection: "row", alignItems: "flex-start", gap: 8 },
  wizardStepNum:     { width: 22, height: 22, borderRadius: 11, alignItems: "center", justifyContent: "center", flexShrink: 0, marginTop: 1 },
  wizardStepNumTxt:  { fontSize: 11, fontWeight: "900" },
  wizardStepTxt:     { flex: 1, fontSize: 12, lineHeight: 18, color: "#CBD5E1" },
  wizardBtn:         { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, height: 44, borderRadius: 11 },
  wizardBtnTxt:      { fontSize: 13, fontWeight: "700", color: "#fff" },
  wizardNote:        { flexDirection: "row", alignItems: "center", gap: 6, paddingTop: 4, borderTopWidth: 1, borderTopColor: "#4285F420" },
  wizardNoteTxt:     { flex: 1, fontSize: 10, color: "#22C55E99" },
  // ── Legacy (kept for compat) ──
  newBadge:          { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 },
  newBadgeTxt:       { fontSize: 9, fontWeight: "800", color: "#fff", letterSpacing: 0.5 },
  providerBtnWide:   { flex: 1, flexDirection: "row", alignItems: "center", gap: 8, paddingVertical: 10, paddingHorizontal: 12, borderRadius: 10 },
  providerBtnSub:    { fontSize: 9, marginTop: 1 },
  hint:              { fontSize: 10, marginTop: 2, marginLeft: 2, color: "#888" },
});

// ─── Exchange API section ─────────────────────────────────────────────────────

type ExchangeId = "mexc" | "binance" | "bybit" | "kucoin";

const EXCHANGES: {
  id: ExchangeId; label: string; color: string; icon: string;
  works: boolean; recommended?: boolean; needsPassphrase?: boolean;
}[] = [
  { id: "mexc",    label: "MEXC",    color: "#1DA1F2", icon: "💧", works: true,  recommended: true },
  { id: "binance", label: "Binance", color: "#F0B90B", icon: "🔶", works: false },
  { id: "bybit",   label: "Bybit",   color: "#F7A600", icon: "🟠", works: false },
  { id: "kucoin",  label: "KuCoin",  color: "#00C076", icon: "🟢", works: false, needsPassphrase: true },
];

const EXCHANGE_GUIDES: Record<ExchangeId, string[]> = {
  binance: [
    "افتح binance.com → الملف الشخصي → إدارة API",
    'اضغط "إنشاء API" — نوع System Generated',
    "فعّل: Spot Trading (بدون Withdrawal أبداً)",
    "اختر IP Restriction: Unrestricted لسهولة الاتصال",
    "ستحصل على: API Key + Secret (بدون Passphrase)",
  ],
  bybit: [
    "افتح bybit.com → الحساب → API",
    'اضغط "Create New Key"',
    "فعّل: Spot Trading فقط (بدون Withdrawal)",
    "اختر IP Restriction: No IP restriction",
    "ستحصل على: API Key + Secret (بدون Passphrase)",
  ],
  mexc: [
    "افتح mexc.com → حساب → API Management",
    'اضغط "Create API" — نوع Standard',
    "فعّل: Spot Read + Spot Trading فقط",
    "لا تفعّل Withdrawal أبداً",
    "ستحصل على: API Key + Secret (بدون Passphrase)",
  ],
  kucoin: [
    "افتح kucoin.com → حساب → API Management",
    'اضغط "Create API" — نوع Trading',
    "فعّل: General + Spot Trading فقط (بدون Withdrawal)",
    "اختر IP Restriction: Unrestricted",
    "ستحصل على: Key + Secret + Passphrase",
  ],
};

// ── ExchangeStatus type from router API ──────────────────────────────────────

interface RouterStatus {
  strategy:        string;
  active_exchange: string;
  any_configured:  boolean;
  exchanges: Record<ExchangeId, {
    configured:        boolean;
    is_active:         boolean;
    needs_pass:        boolean;
    score:             number;
    success_rate:      number;
    trades_ok:         number;
    trades_fail:       number;
    latency_ms:        number;
    consecutive_fails: number;
    api_key_preview:   string;
  }>;
}

// ── Shared ApiField ──────────────────────────────────────────────────────────

function ApiField({
  label, hint, value, onChangeText, placeholder, secure,
  showToggle = false, onToggle, revealed = false, colors,
}: {
  label: string; hint?: string; value: string; onChangeText: (v: string) => void;
  placeholder: string; secure: boolean; showToggle?: boolean;
  onToggle?: () => void; revealed?: boolean; colors: any;
}) {
  return (
    <View style={af.wrap}>
      <View style={af.labelRow}>
        <Text style={[af.label, { color: colors.foreground }]}>{label}</Text>
        {hint ? <Text style={[af.hint, { color: colors.mutedForeground }]}>{hint}</Text> : null}
      </View>
      <View style={[af.inputWrap, { borderColor: value ? `${colors.primary}66` : colors.border, backgroundColor: colors.card }]}>
        <TextInput
          style={[af.input, { color: colors.foreground }]}
          value={value}
          onChangeText={onChangeText}
          placeholder={placeholder}
          placeholderTextColor={colors.mutedForeground}
          secureTextEntry={secure}
          autoCapitalize="none"
          autoCorrect={false}
          spellCheck={false}
        />
        {showToggle && (
          <Pressable style={af.eye} onPress={onToggle}>
            <Feather name={revealed ? "eye-off" : "eye"} size={16} color={colors.mutedForeground} />
          </Pressable>
        )}
      </View>
    </View>
  );
}
const af = StyleSheet.create({
  wrap:      { marginBottom: 12 },
  labelRow:  { marginBottom: 5 },
  label:     { fontSize: 12, fontWeight: "700" },
  hint:      { fontSize: 10, marginTop: 2, lineHeight: 14 },
  inputWrap: { flexDirection: "row", alignItems: "center", borderRadius: 10, borderWidth: 1.5, paddingHorizontal: 12 },
  input:     { flex: 1, height: 44, fontSize: 13, fontFamily: Platform.OS === "ios" ? "Courier New" : "monospace" },
  eye:       { padding: 8 },
});

// ── Single exchange card with collapsible form ────────────────────────────────

function ExchangeCard({
  ex, info, isRouterActive, strategy, onSaved, onSwitched,
}: {
  ex: typeof EXCHANGES[0];
  info: RouterStatus["exchanges"][ExchangeId] | undefined;
  isRouterActive: boolean;
  strategy: string;
  onSaved: () => void;
  onSwitched: (name: string) => void;
}) {
  const colors = useColors();
  const [open,       setOpen]       = useState(false);
  const [apiKey,     setApiKey]     = useState("");
  const [apiSecret,  setApiSecret]  = useState("");
  const [passphrase, setPassphrase] = useState("");
  const [showSec,    setShowSec]    = useState(false);
  const [showPas,    setShowPas]    = useState(false);
  const [saving,     setSaving]     = useState(false);
  const [testing,    setTesting]    = useState(false);
  const [switching,  setSwitching]  = useState(false);
  const [msg,        setMsg]        = useState("");

  const configured = info?.configured ?? false;
  const score      = info?.score ?? 0;
  const latency    = info?.latency_ms ?? 9999;
  const latencyOk  = latency < 5000;

  const statusColor = isRouterActive
    ? ex.color
    : configured
      ? colors.primary
      : "#888";

  const handleSave = async () => {
    if (!apiKey.trim() || !apiSecret.trim()) { setMsg("❌ API Key والـ Secret مطلوبان"); return; }
    if (ex.needsPassphrase && !passphrase.trim()) { setMsg("❌ Passphrase مطلوب لـ KuCoin"); return; }
    setSaving(true); setMsg("");
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    try {
      const r = await fetch(`${getApiBase()}/exchange/credentials`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          exchange:   ex.id,
          api_key:    apiKey.trim(),
          api_secret: apiSecret.trim(),
          passphrase: passphrase.trim(),
        }),
      });
      const d = await safeJson(r);
      if (!d) { setMsg("❌ لا يمكن الوصول للسيرفر — تحقق من الاتصال"); }
      else if (d.success) {
        setMsg(`✅ تم حفظ ${ex.label}`);
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        setApiKey(""); setApiSecret(""); setPassphrase("");
        setOpen(false);
        onSaved();
      } else {
        setMsg(`❌ ${d.detail || "حدث خطأ"}`);
      }
    } catch (e: any) { setMsg(`❌ ${e.message}`); }
    setSaving(false);
    setTimeout(() => setMsg(""), 4000);
  };

  const handleTest = async () => {
    setTesting(true); setMsg("");
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    try {
      const r = await fetch(`${getApiBase()}/exchange/test/${ex.id}`, { method: "POST" });
      const d = await safeJson(r);
      if (!d) { setMsg("❌ لا يمكن الوصول للسيرفر — تحقق من الاتصال"); }
      else {
        setMsg(d.message || (d.success ? "✅ متصل" : "❌ فشل الاتصال"));
        if (d.success) {
          Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
          onSaved();
        }
      }
    } catch (e: any) { setMsg(`❌ ${e.message}`); }
    setTesting(false);
    setTimeout(() => setMsg(""), 6000);
  };

  const handleSwitch = async () => {
    setSwitching(true);
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    try {
      const r = await fetch(`${getApiBase()}/exchange/switch/${ex.id}`, { method: "POST" });
      const d = await safeJson(r);
      if (!d) { setMsg("❌ لا يمكن الوصول للسيرفر"); }
      else if (d.success) {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        onSwitched(ex.id);
      } else {
        setMsg(`❌ ${d.detail || "تعذّر التبديل"}`);
      }
    } catch (e: any) { setMsg(`❌ ${e.message}`); }
    setSwitching(false);
    setTimeout(() => setMsg(""), 4000);
  };

  return (
    <View style={[xc.card, {
      borderColor: isRouterActive ? `${ex.color}88` : colors.border,
      backgroundColor: isRouterActive ? `${ex.color}07` : colors.muted,
      borderWidth: isRouterActive ? 2 : 1,
    }]}>
      {/* ── Card header row ── */}
      <View style={xc.cardHeader}>
        {/* Name + badges */}
        <View style={{ flex: 1 }}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 7 }}>
            <Text style={[xc.cardName, { color: isRouterActive ? ex.color : colors.foreground }]}>{ex.label}</Text>
            {isRouterActive && (
              <View style={[xc.activeBadge, { backgroundColor: ex.color }]}>
                <Text style={xc.activeBadgeTxt}>⚡ نشط</Text>
              </View>
            )}
            {!ex.works && (
              <View style={[xc.blockedBadge, { borderColor: `${colors.mutedForeground}33` }]}>
                <Text style={[xc.blockedBadgeTxt, { color: colors.mutedForeground }]}>محجوب</Text>
              </View>
            )}
            {ex.works && ex.recommended && !configured && (
              <View style={[xc.recBadge, { backgroundColor: `${ex.color}22`, borderColor: `${ex.color}44` }]}>
                <Text style={[xc.recBadgeTxt, { color: ex.color }]}>✓ موصى به</Text>
              </View>
            )}
          </View>
          {configured ? (
            <Text style={[xc.cardSub, { color: colors.mutedForeground }]}>
              {info?.api_key_preview ? `Key: ${info.api_key_preview}` : "مضبوط"}
              {latencyOk && info?.latency_ms !== 9999 ? ` | ${latency}ms` : ""}
              {(info?.trades_ok ?? 0) > 0 ? ` | ✓${info!.trades_ok} ✗${info!.trades_fail}` : ""}
            </Text>
          ) : (
            <Text style={[xc.cardSub, { color: colors.mutedForeground }]}>لم تُضف المفاتيح بعد</Text>
          )}
        </View>

        {/* Score pill */}
        {configured && (
          <View style={[xc.scorePill, { backgroundColor: `${statusColor}18`, borderColor: `${statusColor}33` }]}>
            <Text style={[xc.scoreVal, { color: statusColor }]}>{score.toFixed(0)}</Text>
            <Text style={[xc.scoreLbl, { color: colors.mutedForeground }]}>score</Text>
          </View>
        )}

        {/* Add/Edit toggle */}
        <Pressable
          style={[xc.toggleBtn, {
            backgroundColor: open ? `${ex.color}18` : colors.card,
            borderColor: open ? `${ex.color}55` : colors.border,
          }]}
          onPress={() => { setOpen(v => !v); setMsg(""); }}
        >
          <Feather name={open ? "chevron-up" : (configured ? "edit-2" : "plus")} size={14} color={open ? ex.color : colors.mutedForeground} />
          <Text style={[xc.toggleBtnTxt, { color: open ? ex.color : colors.mutedForeground }]}>
            {open ? "إخفاء" : configured ? "تعديل" : "إضافة"}
          </Text>
        </Pressable>
      </View>

      {/* ── Score bar ── */}
      {configured && (
        <View style={xc.barWrap}>
          <View style={[xc.barTrack, { backgroundColor: colors.border }]}>
            <View style={[xc.barFill, { width: `${Math.min(score, 100)}%` as any, backgroundColor: ex.color }]} />
          </View>
        </View>
      )}

      {/* ── Collapsed: action buttons ── */}
      {!open && configured && (
        <View style={xc.actionRow}>
          {/* Test button */}
          <Pressable
            style={[xc.actionBtn, { borderColor: `${colors.primary}33` }]}
            onPress={handleTest}
            disabled={testing}
          >
            {testing
              ? <ActivityIndicator size="small" color={colors.primary} />
              : <Feather name="wifi" size={12} color={colors.primary} />}
            <Text style={[xc.actionBtnTxt, { color: colors.primary }]}>
              {testing ? "جارٍ..." : "اختبر"}
            </Text>
          </Pressable>
          {/* Switch to this exchange (manual) */}
          {!isRouterActive && strategy === "manual" && (
            <Pressable
              style={[xc.actionBtn, { borderColor: `${ex.color}44`, backgroundColor: `${ex.color}10` }]}
              onPress={handleSwitch}
              disabled={switching}
            >
              {switching
                ? <ActivityIndicator size="small" color={ex.color} />
                : <Feather name="zap" size={12} color={ex.color} />}
              <Text style={[xc.actionBtnTxt, { color: ex.color }]}>
                {switching ? "تبديل..." : "تفعيل"}
              </Text>
            </Pressable>
          )}
        </View>
      )}

      {/* ── Expanded form ── */}
      {open && (
        <View style={xc.form}>
          {/* IP warning for blocked exchanges */}
          {!ex.works && (
            <View style={[xc.warnBox, { backgroundColor: "#FF9F4310", borderColor: "#FF9F4333" }]}>
              <Feather name="alert-triangle" size={12} color="#FF9F43" />
              <Text style={[xc.warnTxt, { color: "#FF9F43" }]}>
                {ex.label} قد تحجب بعض عناوين IP للسيرفرات المشتركة — إذا فشل الاتصال جرّب تفعيل CEX_ALLOW_ALL في الـ backend.
              </Text>
            </View>
          )}

          {/* Guide */}
          <View style={[xc.guide, { backgroundColor: `${ex.color}08`, borderColor: `${ex.color}22` }]}>
            <Text style={[xc.guideTitle, { color: ex.color }]}>كيف تحصل على الـ API Keys من {ex.label}؟</Text>
            {EXCHANGE_GUIDES[ex.id].map((step, i) => (
              <View key={i} style={xc.guideStep}>
                <View style={[xc.stepNum, { backgroundColor: `${ex.color}22` }]}>
                  <Text style={[xc.stepNumTxt, { color: ex.color }]}>{i + 1}</Text>
                </View>
                <Text style={[xc.stepTxt, { color: colors.foreground }]}>{step}</Text>
              </View>
            ))}
          </View>

          <ApiField label="API Key" value={apiKey} onChangeText={setApiKey}
            placeholder={`${ex.label} API Key`} secure={false} colors={colors} />
          <ApiField label="API Secret" value={apiSecret} onChangeText={setApiSecret}
            placeholder={`${ex.label} Secret`} secure={!showSec}
            showToggle onToggle={() => setShowSec(v => !v)} revealed={showSec} colors={colors} />
          {ex.needsPassphrase && (
            <ApiField label="API Passphrase" hint="أنت من حدده عند إنشاء API في KuCoin"
              value={passphrase} onChangeText={setPassphrase} placeholder="Passphrase"
              secure={!showPas} showToggle onToggle={() => setShowPas(v => !v)} revealed={showPas} colors={colors} />
          )}

          <Pressable
            style={[xc.saveBtn, { backgroundColor: saving ? colors.muted : ex.color, opacity: saving ? 0.7 : 1 }]}
            onPress={handleSave} disabled={saving}
          >
            {saving ? <ActivityIndicator size="small" color="#fff" /> : <Feather name="link" size={14} color="#fff" />}
            <Text style={xc.saveBtnTxt}>{saving ? "جارٍ الحفظ..." : `حفظ ${ex.label}`}</Text>
          </Pressable>
        </View>
      )}

      {/* ── Message ── */}
      {!!msg && (
        <Text style={[xc.msg, { color: msg.startsWith("✅") ? colors.primary : msg.startsWith("❌") ? colors.destructive : colors.foreground }]}>
          {msg}
        </Text>
      )}
    </View>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// DEX / بلوكشين Section
// ═══════════════════════════════════════════════════════════════════════════

const DEX_NETWORKS: { id: string; label: string; color: string; emoji: string; chain: string }[] = [
  { id: "base",    label: "Base",    color: "#0052FF", emoji: "🔵", chain: "Chain 8453" },
  { id: "polygon", label: "Polygon", color: "#8247E5", emoji: "🟣", chain: "Chain 137"  },
  { id: "bsc",     label: "BSC",     color: "#F3BA2F", emoji: "🟡", chain: "Chain 56"   },
];

const HYBRID_MODES: { id: string; label: string; desc: string; color: string }[] = [
  { id: "auto",     label: "Auto",     desc: "يقارن DEX مع CEX ويختار الأفضل تلقائياً", color: "#22C55E" },
  { id: "dex_only", label: "DEX فقط", desc: "كل الصفقات عبر البلوكشين مباشرة",         color: "#3B82F6" },
  { id: "cex_only", label: "CEX فقط", desc: "كل الصفقات عبر MEXC أو غيرها",            color: "#F59E0B" },
];

interface DexStatus {
  web3_available: boolean;
  connected:      boolean;
  has_wallet:     boolean;
  network:        string;
  chain_id:       number;
  supported_symbols: string[];
  wallet?: {
    connected:       boolean;
    has_wallet:      boolean;
    address?:        string;
    address_short?:  string;
    native_symbol?:  string;
    native_balance?: number;
    stable_balance?: number;
    stable_symbol?:  string;
    error?:          string;
  };
}

function DexSection() {
  const colors = useColors();

  const [status,      setStatus]      = useState<DexStatus | null>(null);
  const [loading,     setLoading]     = useState(false);
  const [network,     setNetwork]     = useState("base");
  const [privateKey,  setPrivateKey]  = useState("");
  const [rpcUrl,      setRpcUrl]      = useState("");
  const [showKey,     setShowKey]     = useState(false);
  const [_showRpc,    _setShowRpc]    = useState(false);
  const [saving,      setSaving]      = useState(false);
  const [msg,         setMsg]         = useState("");
  const [mode,        setMode]        = useState("auto");
  const [modeMsg,     setModeMsg]     = useState("");
  const [openForm,    setOpenForm]    = useState(false);
  const [quoting,     setQuoting]     = useState(false);
  const [quoteResult, setQuoteResult] = useState("");

  const loadStatus = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${getApiBase()}/dex/status`);
      const d = await safeJson<DexStatus>(r);
      if (d) {
        setStatus(d);
        setNetwork(d.network?.toLowerCase() ?? "base");
      }
    } catch { /* ignore */ }

    try {
      const r2 = await fetch(`${getApiBase()}/dex/hybrid-stats`);
      const s = await safeJson(r2);
      if (s) setMode(s.mode ?? "auto");
    } catch { /* ignore */ }

    setLoading(false);
  }, []);

  useEffect(() => { loadStatus(); }, [loadStatus]);

  const handleSave = async () => {
    if (!privateKey.trim() && !rpcUrl.trim()) {
      // Only saving network change
    }
    setSaving(true); setMsg("");
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    try {
      const r = await fetch(`${getApiBase()}/dex/configure`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          network:     network,
          private_key: privateKey.trim(),
          rpc_url:     rpcUrl.trim(),
        }),
      });
      const d = await safeJson(r);
      if (!d) { setMsg("❌ لا يمكن الوصول للسيرفر"); }
      else if (d.success) {
        setMsg(`✅ ${d.message || "تم حفظ إعدادات DEX"}`);
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        setPrivateKey(""); setRpcUrl("");
        setOpenForm(false);
        await loadStatus();
      } else {
        setMsg(`❌ ${d.detail || d.error || "حدث خطأ"}`);
      }
    } catch (e: any) { setMsg(`❌ ${e.message}`); }
    setSaving(false);
    setTimeout(() => setMsg(""), 5000);
  };

  const handleSetMode = async (newMode: string) => {
    setMode(newMode);
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    try {
      const r = await fetch(`${getApiBase()}/dex/mode`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: newMode, cex_advantage_pct: 0.3 }),
      });
      const d = await safeJson(r);
      if (d?.success) {
        setModeMsg(`✅ وضع التوجيه: ${newMode}`);
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      } else {
        setModeMsg(`❌ ${d.detail || "فشل"}`);
      }
    } catch (e: any) { setModeMsg(`❌ ${e.message}`); }
    setTimeout(() => setModeMsg(""), 3000);
  };

  const handleQuote = async () => {
    setQuoting(true); setQuoteResult("");
    try {
      const r = await fetch(`${getApiBase()}/dex/compare/ETH-USDT?amount=100`);
      const d = await safeJson(r);
      if (d.dex_quote?.success) {
        const dexP  = d.dex_quote.price?.toFixed(2) ?? "—";
        const cexP  = d.cex_price?.toFixed(2) ?? "—";
        const route = d.decision?.route?.toUpperCase() ?? "—";
        setQuoteResult(`DEX: $${dexP} | CEX: $${cexP} → المختار: ${route}\n${d.decision?.reason ?? ""}`);
      } else {
        setQuoteResult(`DEX: ${d.dex_quote?.error ?? "لا سيولة"} | CEX: $${d.cex_price?.toFixed(2) ?? "—"}`);
      }
    } catch (e: any) { setQuoteResult(`❌ ${e.message}`); }
    setQuoting(false);
  };

  const connected   = status?.connected ?? false;
  const hasWallet   = status?.has_wallet ?? false;
  const walletInfo  = status?.wallet;
  const currentNet  = DEX_NETWORKS.find(n => n.id === network) ?? DEX_NETWORKS[0];

  return (
    <View>

      {/* ── Status bar ── */}
      <View style={[dx.statusBar, {
        backgroundColor: connected ? `${currentNet.color}10` : `${colors.destructive}0A`,
        borderColor:     connected ? `${currentNet.color}33` : `${colors.destructive}22`,
      }]}>
        <View style={[dx.statusDot, {
          backgroundColor: connected
            ? (hasWallet ? currentNet.color : "#F59E0B")
            : colors.destructive,
        }]} />
        <View style={{ flex: 1 }}>
          <Text style={[dx.statusTitle, { color: colors.foreground }]}>
            {connected
              ? hasWallet
                ? `${currentNet.emoji} ${currentNet.label} — محفظة متصلة`
                : `${currentNet.emoji} ${currentNet.label} — شبكة متصلة (لا محفظة بعد)`
              : "⚫ غير متصل بالبلوكشين"}
          </Text>
          {hasWallet && walletInfo?.address_short ? (
            <Text style={[dx.statusSub, { color: colors.mutedForeground, fontFamily: "monospace" }]}>
              {walletInfo.address_short}
              {walletInfo.stable_balance !== undefined
                ? `  |  ${walletInfo.stable_balance} ${walletInfo.stable_symbol}`
                : ""}
              {walletInfo.native_balance !== undefined
                ? `  |  ${walletInfo.native_balance} ${walletInfo.native_symbol}`
                : ""}
            </Text>
          ) : (
            <Text style={[dx.statusSub, { color: colors.mutedForeground }]}>
              {connected ? "أضف مفتاح المحفظة الخاصة لتفعيل التداول" : "تحقق من اتصال الإنترنت"}
            </Text>
          )}
        </View>
        {loading && <ActivityIndicator size="small" color={colors.mutedForeground} />}
      </View>

      {/* ── Halal notice ── */}
      <InfoBox
        icon="shield"
        text="DEX Spot Swap حلال بالكامل — لا رافعة، لا استقراض، لا ربا. رسوم الـ Gas تكلفة معاملة مقبولة شرعاً."
        color="#22C55E"
      />

      {/* ── Network selector ── */}
      <Text style={[dx.sectionLabel, { color: colors.mutedForeground, marginTop: 14 }]}>اختر الشبكة</Text>
      <View style={dx.networkRow}>
        {DEX_NETWORKS.map(net => {
          const active = network === net.id;
          return (
            <Pressable
              key={net.id}
              style={[dx.netCard, {
                borderColor:     active ? net.color : colors.border,
                backgroundColor: active ? `${net.color}15` : colors.card,
                flex: 1,
              }]}
              onPress={() => setNetwork(net.id)}
            >
              <Text style={dx.netEmoji}>{net.emoji}</Text>
              <Text style={[dx.netLabel, { color: active ? net.color : colors.foreground }]}>{net.label}</Text>
              <Text style={[dx.netChain, { color: colors.mutedForeground }]}>{net.chain}</Text>
            </Pressable>
          );
        })}
      </View>

      {/* ── Routing mode ── */}
      <Text style={[dx.sectionLabel, { color: colors.mutedForeground, marginTop: 16 }]}>وضع التوجيه</Text>
      <View style={dx.modeRow}>
        {HYBRID_MODES.map(m => {
          const active = mode === m.id;
          return (
            <Pressable
              key={m.id}
              style={[dx.modeCard, {
                borderColor:     active ? m.color : colors.border,
                backgroundColor: active ? `${m.color}15` : colors.card,
                flex: 1,
              }]}
              onPress={() => handleSetMode(m.id)}
            >
              <View style={[dx.modeDot, { backgroundColor: active ? m.color : colors.muted }]} />
              <Text style={[dx.modeLabel, { color: active ? m.color : colors.foreground }]}>{m.label}</Text>
            </Pressable>
          );
        })}
      </View>
      {DEX_NETWORKS.find(n => n.id === network) && (
        <Text style={[dx.modeDesc, { color: colors.mutedForeground }]}>
          {HYBRID_MODES.find(m => m.id === mode)?.desc ?? ""}
        </Text>
      )}
      {modeMsg ? (
        <Text style={[dx.modeMsg, { color: modeMsg.startsWith("✅") ? "#22C55E" : colors.destructive }]}>{modeMsg}</Text>
      ) : null}

      {/* ── Quote tester ── */}
      <Pressable
        style={[dx.quoteBtn, { borderColor: `${currentNet.color}44`, backgroundColor: `${currentNet.color}0A` }]}
        onPress={handleQuote}
        disabled={quoting || !connected}
      >
        {quoting
          ? <ActivityIndicator size="small" color={currentNet.color} />
          : <Feather name="zap" size={14} color={currentNet.color} />
        }
        <Text style={[dx.quoteBtnTxt, { color: currentNet.color }]}>اختبر سعر ETH/USDT: DEX vs CEX</Text>
      </Pressable>
      {quoteResult ? (
        <Text style={[dx.quoteResult, { color: colors.mutedForeground }]}>{quoteResult}</Text>
      ) : null}

      {/* ── Wallet config toggle ── */}
      <Pressable
        style={[dx.configToggle, { borderColor: colors.border }]}
        onPress={() => setOpenForm(v => !v)}
      >
        <Feather name="key" size={14} color={colors.mutedForeground} />
        <Text style={[dx.configToggleTxt, { color: colors.foreground }]}>
          {openForm ? "إخفاء إعدادات المحفظة" : "إعداد مفتاح المحفظة الخاصة"}
        </Text>
        <Feather name={openForm ? "chevron-up" : "chevron-down"} size={14} color={colors.mutedForeground} />
      </Pressable>

      {openForm && (
        <View style={[dx.formWrap, { borderColor: colors.border, backgroundColor: `${colors.card}` }]}>

          <Text style={[dx.formNote, { color: colors.mutedForeground }]}>
            🔒 المفتاح الخاص يُحفظ محلياً في ملف .env على الخادم فقط — لا يُرسل لأي طرف خارجي أبداً.
          </Text>

          <ApiField
            label="المفتاح الخاص (Private Key)"
            hint="يبدأ بـ 0x — 64 حرف hex"
            value={privateKey}
            onChangeText={setPrivateKey}
            placeholder="0xabc123..."
            secure={!showKey}
            showToggle
            onToggle={() => setShowKey(v => !v)}
            revealed={showKey}
            colors={colors}
          />

          <ApiField
            label="RPC مخصص (اختياري)"
            hint="Alchemy أو Infura — اتركه فارغاً للـ public RPC"
            value={rpcUrl}
            onChangeText={setRpcUrl}
            placeholder="https://base-mainnet.g.alchemy.com/v2/..."
            secure={false}
            colors={colors}
          />

          <Pressable
            style={[dx.saveBtn, { backgroundColor: currentNet.color, opacity: saving ? 0.7 : 1 }]}
            onPress={handleSave}
            disabled={saving}
          >
            {saving
              ? <ActivityIndicator size="small" color="#fff" />
              : <Feather name="save" size={16} color="#fff" />
            }
            <Text style={dx.saveBtnTxt}>حفظ إعدادات DEX</Text>
          </Pressable>
        </View>
      )}

      {msg ? (
        <Text style={[dx.msg, { color: msg.startsWith("✅") ? "#22C55E" : colors.destructive }]}>{msg}</Text>
      ) : null}
    </View>
  );
}

const dx = StyleSheet.create({
  statusBar:      { flexDirection: "row", alignItems: "center", gap: 10, padding: 12, borderRadius: 12, borderWidth: 1, marginBottom: 4 },
  statusDot:      { width: 8, height: 8, borderRadius: 4 },
  statusTitle:    { fontSize: 13, fontWeight: "700" },
  statusSub:      { fontSize: 11, marginTop: 2 },

  sectionLabel:   { fontSize: 10, fontWeight: "700", letterSpacing: 0.8, textTransform: "uppercase", marginBottom: 6 },

  networkRow:     { flexDirection: "row", gap: 6 },
  netCard:        { alignItems: "center", padding: 10, borderRadius: 11, borderWidth: 1.5, gap: 3 },
  netEmoji:       { fontSize: 18 },
  netLabel:       { fontSize: 12, fontWeight: "700" },
  netChain:       { fontSize: 9, letterSpacing: 0.3 },

  modeRow:        { flexDirection: "row", gap: 6 },
  modeCard:       { flexDirection: "row", alignItems: "center", gap: 6, padding: 10, borderRadius: 11, borderWidth: 1.5 },
  modeDot:        { width: 7, height: 7, borderRadius: 3.5 },
  modeLabel:      { fontSize: 12, fontWeight: "700" },
  modeDesc:       { fontSize: 11, marginTop: 6, lineHeight: 16 },
  modeMsg:        { fontSize: 12, textAlign: "center", marginTop: 4 },

  quoteBtn:       { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, height: 40, borderRadius: 10, borderWidth: 1, marginTop: 12 },
  quoteBtnTxt:    { fontSize: 13, fontWeight: "600" },
  quoteResult:    { fontSize: 11, marginTop: 6, lineHeight: 17, textAlign: "center", paddingHorizontal: 4 },

  configToggle:   { flexDirection: "row", alignItems: "center", gap: 8, paddingVertical: 12, borderTopWidth: 1, marginTop: 12 },
  configToggleTxt:{ flex: 1, fontSize: 13, fontWeight: "600" },

  formWrap:       { borderRadius: 12, borderWidth: 1, padding: 14, gap: 2, marginTop: 6 },
  formNote:       { fontSize: 11, lineHeight: 16, marginBottom: 10 },
  saveBtn:        { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, height: 44, borderRadius: 11, marginTop: 8 },
  saveBtnTxt:     { fontSize: 14, fontWeight: "700", color: "#fff" },
  msg:            { fontSize: 12, textAlign: "center", marginTop: 6 },
});

// ── Main exchange section ─────────────────────────────────────────────────────

function ExchangeSection() {
  const colors = useColors();
  const [routerStatus, setRouterStatus] = useState<RouterStatus | null>(null);
  const [switchingStrategy, setSwitchingStrategy] = useState(false);
  const [stratMsg, setStratMsg] = useState("");

  const loadStatus = useCallback(async () => {
    try {
      const r = await fetch(`${getApiBase()}/exchange/status`);
      const d = await safeJson(r);
      if (d) setRouterStatus(d);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { loadStatus(); }, [loadStatus]);

  const strategy      = routerStatus?.strategy ?? "auto";
  const activeExchange = routerStatus?.active_exchange ?? "mexc";
  const anyConfigured  = routerStatus?.any_configured ?? false;
  const isAuto         = strategy === "auto";

  const toggleStrategy = async () => {
    const next = isAuto ? "manual" : "auto";
    setSwitchingStrategy(true);
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    try {
      await fetch(`${getApiBase()}/exchange/strategy`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ strategy: next }),
      });
      setStratMsg(next === "auto" ? "✅ وضع Auto — البوت يختار الأفضل تلقائياً" : "✅ وضع Manual — اختر البورصة يدوياً");
      await loadStatus();
    } catch { setStratMsg("❌ تعذّر التغيير"); }
    setSwitchingStrategy(false);
    setTimeout(() => setStratMsg(""), 3000);
  };

  return (
    <View style={xc.wrap}>

      {/* ── Strategy toggle bar ── */}
      <View style={[xc.stratBar, { backgroundColor: isAuto ? `${colors.primary}10` : `${colors.card}`, borderColor: isAuto ? `${colors.primary}33` : colors.border }]}>
        <View style={{ flex: 1 }}>
          <Text style={[xc.stratTitle, { color: colors.foreground }]}>
            {isAuto ? "⚡ Auto Router — يختار الأفضل تلقائياً" : "🎯 Manual — اختر البورصة يدوياً"}
          </Text>
          <Text style={[xc.stratSub, { color: colors.mutedForeground }]}>
            {isAuto
              ? "يحسب الـ Score من: معدل النجاح ٧٠٪ + سرعة الاتصال ٣٠٪"
              : "البوت يستخدم البورصة التي تضغط عليها \"تفعيل\""}
          </Text>
        </View>
        <Pressable
          style={[xc.stratToggle, { backgroundColor: isAuto ? colors.primary : colors.muted, borderColor: isAuto ? colors.primary : colors.border }]}
          onPress={toggleStrategy}
          disabled={switchingStrategy}
        >
          {switchingStrategy
            ? <ActivityIndicator size="small" color={isAuto ? "#fff" : colors.foreground} />
            : <Text style={[xc.stratToggleTxt, { color: isAuto ? "#fff" : colors.foreground }]}>
                {isAuto ? "Auto" : "Manual"}
              </Text>
          }
        </Pressable>
      </View>

      {stratMsg ? (
        <Text style={[xc.stratMsg, { color: stratMsg.startsWith("✅") ? colors.primary : colors.destructive }]}>{stratMsg}</Text>
      ) : null}

      {/* ── Active exchange summary ── */}
      {anyConfigured && (
        <View style={[xc.activeSummary, { backgroundColor: colors.muted, borderColor: colors.border }]}>
          <Feather name="activity" size={13} color={colors.primary} />
          <Text style={[xc.activeSummaryTxt, { color: colors.foreground }]}>
            البورصة النشطة الآن:{" "}
            <Text style={{ fontWeight: "800", color: colors.primary }}>{activeExchange.toUpperCase()}</Text>
            {routerStatus?.exchanges[activeExchange as ExchangeId]?.latency_ms !== 9999
              ? `  |  ${routerStatus?.exchanges[activeExchange as ExchangeId]?.latency_ms}ms`
              : ""}
          </Text>
        </View>
      )}

      {/* ── CEX notice ── */}
      <View style={[xc.infoBox, { backgroundColor: "#3B82F610", borderColor: "#3B82F633" }]}>
        <Feather name="info" size={12} color="#3B82F6" />
        <Text style={[xc.infoTxt, { color: "#3B82F6" }]}>
          MEXC هو الأكثر توافقاً مع السيرفرات الأمريكية. تأكد من تفعيل CEX_ALLOW_ALL=true في بيئة Render لفتح باقي البورصات.
        </Text>
      </View>

      {/* ── Exchange cards ── */}
      {EXCHANGES.map(ex => (
        <ExchangeCard
          key={ex.id}
          ex={ex}
          info={routerStatus?.exchanges[ex.id]}
          isRouterActive={activeExchange === ex.id && anyConfigured}
          strategy={strategy}
          onSaved={loadStatus}
          onSwitched={(name) => {
            setStratMsg(`✅ تم التبديل إلى ${name.toUpperCase()}`);
            loadStatus();
            setTimeout(() => setStratMsg(""), 3000);
          }}
        />
      ))}
    </View>
  );
}

const xc = StyleSheet.create({
  wrap:            { gap: 10 },
  stratBar:        { flexDirection: "row", alignItems: "center", gap: 12, padding: 14, borderRadius: 14, borderWidth: 1 },
  stratTitle:      { fontSize: 13, fontWeight: "800" },
  stratSub:        { fontSize: 10, marginTop: 3, lineHeight: 14 },
  stratToggle:     { paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10, borderWidth: 1 },
  stratToggleTxt:  { fontSize: 12, fontWeight: "800" },
  stratMsg:        { fontSize: 11, textAlign: "center", marginTop: -4 },
  activeSummary:   { flexDirection: "row", alignItems: "center", gap: 8, padding: 10, borderRadius: 10, borderWidth: 1 },
  activeSummaryTxt:{ fontSize: 12, flex: 1 },
  infoBox:         { flexDirection: "row", alignItems: "flex-start", gap: 8, padding: 10, borderRadius: 10, borderWidth: 1 },
  infoTxt:         { flex: 1, fontSize: 11, lineHeight: 16 },

  card:        { borderRadius: 14, padding: 14, gap: 8 },
  cardHeader:  { flexDirection: "row", alignItems: "center", gap: 10 },
  cardName:    { fontSize: 15, fontWeight: "800" },
  cardSub:     { fontSize: 10, marginTop: 2, fontFamily: Platform.OS === "ios" ? "Courier New" : "monospace" },
  activeBadge: { paddingHorizontal: 7, paddingVertical: 2, borderRadius: 6 },
  activeBadgeTxt: { fontSize: 9, fontWeight: "800", color: "#fff" },
  blockedBadge:   { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6, borderWidth: 1 },
  blockedBadgeTxt:{ fontSize: 9, fontWeight: "600" },
  recBadge:       { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6, borderWidth: 1 },
  recBadgeTxt:    { fontSize: 9, fontWeight: "700" },

  scorePill:   { alignItems: "center", justifyContent: "center", width: 46, height: 46, borderRadius: 23, borderWidth: 1 },
  scoreVal:    { fontSize: 15, fontWeight: "800" },
  scoreLbl:    { fontSize: 8, fontWeight: "600", marginTop: -1 },

  toggleBtn:   { flexDirection: "row", alignItems: "center", gap: 5, paddingHorizontal: 10, paddingVertical: 8, borderRadius: 10, borderWidth: 1 },
  toggleBtnTxt:{ fontSize: 11, fontWeight: "700" },

  barWrap:   { paddingHorizontal: 2 },
  barTrack:  { height: 3, borderRadius: 2, overflow: "hidden" },
  barFill:   { height: 3, borderRadius: 2 },

  actionRow: { flexDirection: "row", gap: 8 },
  actionBtn: { flexDirection: "row", alignItems: "center", gap: 5, paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8, borderWidth: 1 },
  actionBtnTxt: { fontSize: 11, fontWeight: "700" },

  form:      { gap: 0, marginTop: 4 },
  warnBox:   { flexDirection: "row", alignItems: "flex-start", gap: 7, padding: 10, borderRadius: 10, borderWidth: 1, marginBottom: 10 },
  warnTxt:   { flex: 1, fontSize: 11, lineHeight: 16 },
  guide:     { padding: 12, borderRadius: 10, borderWidth: 1, marginBottom: 12, gap: 6 },
  guideTitle:{ fontSize: 11, fontWeight: "800", marginBottom: 2 },
  guideStep: { flexDirection: "row", alignItems: "flex-start", gap: 7 },
  stepNum:   { width: 18, height: 18, borderRadius: 9, alignItems: "center", justifyContent: "center" },
  stepNumTxt:{ fontSize: 9, fontWeight: "800" },
  stepTxt:   { flex: 1, fontSize: 10, lineHeight: 15, paddingTop: 2 },
  saveBtn:   { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 7, height: 46, borderRadius: 12, marginTop: 2 },
  saveBtnTxt:{ fontSize: 14, fontWeight: "700", color: "#fff" },
  msg:       { fontSize: 11, textAlign: "center", marginTop: 2, lineHeight: 16 },
});

// ─── Database URL Panel ───────────────────────────────────────────────────────

function DatabaseUrlPanel() {
  const colors   = useColors();
  const [url,     setUrl]     = useState("");
  const [label,   setLabel]   = useState("");
  const [testing, setTesting] = useState(false);
  const [saving,  setSaving]  = useState(false);
  const [msg,     setMsg]     = useState("");
  const [dbInfo,  setDbInfo]  = useState<{ source?: string; connected?: boolean } | null>(null);

  useEffect(() => {
    fetch(`${getApiBase()}/db/status`)
      .then(r => safeJson<{ source?: string; connected?: boolean }>(r))
      .then(d => { if (d) setDbInfo(d); })
      .catch(() => {});
  }, []);

  const showMsg = (m: string, ttl = 6000) => {
    setMsg(m);
    setTimeout(() => setMsg(""), ttl);
  };

  const handleTest = async () => {
    if (!url.trim()) { showMsg("❌ أدخل رابط قاعدة البيانات أولاً"); return; }
    setTesting(true); setMsg("⏳ جارٍ اختبار الاتصال...");
    try {
      const r = await fetch(`${getApiBase()}/db/test-url`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url.trim() }),
      });
      const d = await safeJson<{ success?: boolean; source?: string; error?: string; message?: string }>(r);
      if (!d) showMsg("❌ لا يمكن الوصول للسيرفر — تحقق من رابط الخادم");
      else     showMsg(d.success ? `✅ ${d.message || "اتصال ناجح"}` : `❌ ${d.error}`);
    } catch (e: any) { showMsg(`❌ ${e.message}`); }
    setTesting(false);
  };

  const handleSave = async () => {
    if (!url.trim()) { showMsg("❌ أدخل رابط قاعدة البيانات أولاً"); return; }
    setSaving(true); setMsg("⏳ جارٍ الاتصال والحفظ...");
    try {
      const r = await fetch(`${getApiBase()}/db/update-url`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url.trim(), label: label.trim() }),
      });
      const d = await safeJson<{ success?: boolean; source?: string; error?: string; message?: string }>(r);
      if (!d) {
        showMsg("❌ لا يمكن الوصول للسيرفر");
      } else if (d.success) {
        showMsg(`✅ ${d.message}`);
        setDbInfo({ source: d.source, connected: true });
        setUrl(""); setLabel("");
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      } else {
        showMsg(`❌ ${d.error}`);
      }
    } catch (e: any) { showMsg(`❌ ${e.message}`); }
    setSaving(false);
  };

  const connected = dbInfo?.connected !== false;
  const source    = dbInfo?.source ?? "Replit PostgreSQL";

  return (
    <View style={[s.card, { borderColor: colors.border, marginHorizontal: 16 }]}>
      {/* Header */}
      <View style={{ flexDirection: "row", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <View style={{ width: 3, height: 14, borderRadius: 2, backgroundColor: "#10B981" }} />
        <Text style={{ fontSize: 10, fontWeight: "700", letterSpacing: 1.5, color: colors.mutedForeground }}>
          قاعدة البيانات
        </Text>
      </View>

      {/* Current connection */}
      <View style={{
        flexDirection: "row", alignItems: "center", gap: 8,
        padding: 10, borderRadius: 10, marginBottom: 14,
        backgroundColor: connected ? "#10B98110" : "#EF444410",
        borderWidth: 1, borderColor: connected ? "#10B98130" : "#EF444430",
      }}>
        <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: connected ? "#10B981" : "#EF4444" }} />
        <Text style={{ fontSize: 11, color: connected ? "#10B981" : "#EF4444", flex: 1 }}>
          {connected ? `متصل — ${source}` : `غير متصل — ${source}`}
        </Text>
      </View>

      {/* URL input */}
      <Text style={{ fontSize: 11, color: colors.mutedForeground, marginBottom: 5 }}>رابط قاعدة البيانات</Text>
      <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, backgroundColor: colors.muted, paddingHorizontal: 12, marginBottom: 8, minHeight: 42, justifyContent: "center" }}>
        <TextInput
          value={url}
          onChangeText={setUrl}
          placeholder="postgresql://user:pass@host/db?sslmode=require"
          placeholderTextColor={colors.mutedForeground}
          style={{ fontSize: 12, color: colors.foreground, fontFamily: Platform.OS === "ios" ? "Courier New" : "monospace" }}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
        />
      </View>

      {/* Label input */}
      <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 10, backgroundColor: colors.muted, paddingHorizontal: 12, marginBottom: 12, height: 40, justifyContent: "center" }}>
        <TextInput
          value={label}
          onChangeText={setLabel}
          placeholder="الاسم (اختياري — مثال: Neon Backup)"
          placeholderTextColor={colors.mutedForeground}
          style={{ fontSize: 13, color: colors.foreground }}
        />
      </View>

      {/* Buttons */}
      <View style={{ flexDirection: "row", gap: 8, marginBottom: 8 }}>
        <Pressable
          onPress={handleTest}
          disabled={testing || saving}
          style={{
            flex: 1, height: 40, borderRadius: 10, borderWidth: 1,
            borderColor: "#22C55E", alignItems: "center", justifyContent: "center",
            flexDirection: "row", gap: 6, opacity: testing ? 0.6 : 1,
          }}
        >
          {testing ? <ActivityIndicator size="small" color="#22C55E" /> : <Feather name="wifi" size={13} color="#22C55E" />}
          <Text style={{ fontSize: 13, fontWeight: "700", color: "#22C55E" }}>اختبار</Text>
        </Pressable>

        <Pressable
          onPress={handleSave}
          disabled={saving || testing}
          style={{
            flex: 2, height: 40, borderRadius: 10,
            backgroundColor: saving ? colors.muted : "#10B981",
            alignItems: "center", justifyContent: "center",
            flexDirection: "row", gap: 6, opacity: saving ? 0.6 : 1,
          }}
        >
          {saving ? <ActivityIndicator size="small" color="#fff" /> : <Feather name="database" size={13} color="#fff" />}
          <Text style={{ fontSize: 13, fontWeight: "700", color: "#fff" }}>
            {saving ? "جارٍ الاتصال..." : "إضافة السيرفر"}
          </Text>
        </Pressable>
      </View>

      {!!msg && (
        <Text style={{ fontSize: 11, textAlign: "center", lineHeight: 16,
          color: msg.startsWith("✅") ? "#10B981" : msg.startsWith("⏳") ? colors.mutedForeground : "#EF4444",
        }}>{msg}</Text>
      )}

      {/* Help guide */}
      <View style={{ marginTop: 10, padding: 10, borderRadius: 10, backgroundColor: "#3B82F608", borderWidth: 1, borderColor: "#3B82F622" }}>
        <Text style={{ fontSize: 9, fontWeight: "700", color: "#3B82F6", marginBottom: 4 }}>كيفية الحصول على الرابط:</Text>
        <Text style={{ fontSize: 10, color: colors.mutedForeground, lineHeight: 16 }}>
          {"• Neon.tech → New Project → Settings → Connection string → URI\n"}
          {"• Supabase → Settings → Database → Connection string → URI\n"}
          {"• Railway → Variables → DATABASE_URL\n"}
          {"• الرابط يبدأ بـ postgresql:// أو postgres://"}
        </Text>
      </View>
    </View>
  );
}

// ─── Server Pool Panel ───────────────────────────────────────────────────────

function ServerPoolPanel() {
  const colors  = useColors();
  const [nodes,     setNodes]     = useState<any[]>([]);
  const [loading,   setLoading]   = useState(false);
  const [pinging,   setPinging]   = useState(false);
  const [addUrl,    setAddUrl]    = useState("");
  const [addLabel,  setAddLabel]  = useState("");
  const [adding,    setAdding]    = useState(false);
  const [msg,       setMsg]       = useState("");
  const [power,     setPower]     = useState<any>(null);

  const load = useCallback(async () => {
    try {
      const base = getApiBase();
      const [nr, pr] = await Promise.all([
        fetch(`${base}/nodes`).then(r => safeJson(r)),
        fetch(`${base}/power`).then(r => safeJson(r)),
      ]);
      setNodes(nr?.nodes ?? []);
      setPower(pr ?? null);
    } catch { /* silent */ }
  }, []);

  useEffect(() => { setLoading(true); load().finally(() => setLoading(false)); }, [load]);

  const handleAdd = async () => {
    if (!addUrl.trim()) return;
    setAdding(true); setMsg("");
    try {
      const base = getApiBase();
      const r = await fetch(`${base}/nodes/add`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: addUrl.trim(), label: addLabel.trim() }),
      });
      const res = await safeJson(r);
      if (!res) {
        setMsg("❌ لا يمكن الوصول للسيرفر — تحقق من الرابط");
      } else if (res.success) {
        setMsg(`✅ ${res.message}`);
        setAddUrl(""); setAddLabel("");
        await load();
      } else {
        setMsg(`❌ ${res.error || res.detail || "فشل الاتصال"}`);
      }
    } catch (e: any) { setMsg(`❌ ${e.message}`); }
    setAdding(false);
  };

  const handlePingAll = async () => {
    setPinging(true); setMsg("");
    try {
      const base = getApiBase();
      const r = await fetch(`${base}/nodes/ping-all`, { method: "POST" });
      const res = await safeJson(r);
      if (res) setMsg(`✅ تم الـ ping على ${res.pinged} سيرفر`);
      else setMsg("❌ لا يمكن الوصول للسيرفر");
      await load();
    } catch (e: any) { setMsg(`❌ ${e.message}`); }
    setPinging(false);
  };

  const handleRemove = async (nodeId: string) => {
    try {
      const base = getApiBase();
      await fetch(`${base}/nodes/${encodeURIComponent(nodeId)}`, { method: "DELETE" });
      await load();
    } catch { /* silent */ }
  };

  const scoreColor = !power ? "#6B7280"
    : power.score >= 70 ? "#10B981"
    : power.score >= 50 ? "#F59E0B"
    : "#EF4444";

  return (
    <View style={[s.section, { paddingHorizontal: 16 }]}>
      {/* Section header */}
      <View style={{ flexDirection: "row", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <View style={{ width: 3, height: 14, borderRadius: 2, backgroundColor: "#6366F1" }} />
        <Text style={{ fontSize: 10, fontWeight: "700", letterSpacing: 1.5, color: colors.mutedForeground }}>
          POWER & SERVER POOL
        </Text>
      </View>

      {/* Global Power Card */}
      {power && (
        <View style={[s.card, { borderColor: `${scoreColor}44`, backgroundColor: colors.card, marginBottom: 12 }]}>
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
            <View style={{ gap: 2 }}>
              <Text style={{ fontSize: 9, fontWeight: "700", letterSpacing: 1.5, color: colors.mutedForeground }}>
                GLOBAL POWER RATING
              </Text>
              <Text style={{ fontSize: 22, fontWeight: "800", color: scoreColor }}>
                {power.score}%
                <Text style={{ fontSize: 14, fontWeight: "500", color: colors.mutedForeground }}> — {power.label}</Text>
              </Text>
              <Text style={{ fontSize: 11, color: colors.mutedForeground }}>{power.global_rank}</Text>
            </View>
            <View style={{
              width: 52, height: 52, borderRadius: 26,
              backgroundColor: `${scoreColor}18`,
              borderWidth: 2, borderColor: `${scoreColor}44`,
              alignItems: "center", justifyContent: "center",
            }}>
              <Text style={{ fontSize: 22, fontWeight: "800", color: scoreColor }}>{power.grade}</Text>
            </View>
          </View>

          {/* Progress bar */}
          <View style={{ height: 4, borderRadius: 2, backgroundColor: colors.muted, marginTop: 8 }}>
            <View style={{ height: 4, borderRadius: 2, backgroundColor: scoreColor, width: `${power.score}%` as any }} />
          </View>

          {/* Breakdown */}
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 10 }}>
            {Object.values(power.breakdown as Record<string, any>).map((b: any) => {
              const ratio = b.score / b.max;
              const c = ratio >= 0.8 ? "#10B981" : ratio >= 0.5 ? "#F59E0B" : "#EF4444";
              return (
                <View key={b.label} style={{
                  paddingHorizontal: 8, paddingVertical: 4, borderRadius: 8,
                  backgroundColor: `${c}12`, borderWidth: 1, borderColor: `${c}33`,
                  flexDirection: "row", alignItems: "center", gap: 4,
                }}>
                  <Text style={{ fontSize: 9, color: c, fontWeight: "700" }}>{b.score}/{b.max}</Text>
                  <Text style={{ fontSize: 9, color: colors.mutedForeground }}>{b.label}</Text>
                </View>
              );
            })}
          </View>

          {/* Tips */}
          {(power.tips ?? []).length > 0 && (
            <View style={{ marginTop: 8, padding: 8, borderRadius: 8, backgroundColor: `${scoreColor}08` }}>
              <Text style={{ fontSize: 9, fontWeight: "700", color: scoreColor, marginBottom: 4 }}>لترقية الدرجة:</Text>
              {(power.tips as string[]).map((tip, i) => (
                <Text key={i} style={{ fontSize: 10, color: colors.mutedForeground, lineHeight: 16 }}>• {tip}</Text>
              ))}
            </View>
          )}
        </View>
      )}

      {/* Server nodes list */}
      <View style={[s.card, { borderColor: `#6366F144`, backgroundColor: colors.card }]}>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
          <Text style={{ fontSize: 13, fontWeight: "700", color: colors.foreground }}>🖥️ خوادم الكلستر</Text>
          <Pressable
            onPress={handlePingAll}
            disabled={pinging}
            style={{ paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8, backgroundColor: "#6366F118", borderWidth: 1, borderColor: "#6366F144" }}
          >
            {pinging ? <ActivityIndicator size="small" color="#6366F1" /> : (
              <Text style={{ fontSize: 11, color: "#6366F1", fontWeight: "600" }}>⚡ Ping الكل</Text>
            )}
          </Pressable>
        </View>

        {loading ? <ActivityIndicator color="#6366F1" /> : nodes.length === 0 ? (
          <Text style={{ fontSize: 12, color: colors.mutedForeground, textAlign: "center", padding: 8 }}>
            لا يوجد سيرفرات خارجية — السيرفر الحالي فقط يعمل
          </Text>
        ) : nodes.map((n: any) => {
          const isLeader  = n.is_leader;
          const latency   = n.latency_ms ?? 0;
          const latColor  = latency <= 0 ? "#6B7280" : latency < 200 ? "#10B981" : latency < 600 ? "#F59E0B" : "#EF4444";
          const age       = n.age_seconds ?? 9999;
          const alive     = age < 75;
          return (
            <View key={n.node_id} style={{
              flexDirection: "row", alignItems: "center", gap: 8,
              paddingVertical: 8, borderTopWidth: 1, borderTopColor: colors.border,
            }}>
              <View style={{
                width: 8, height: 8, borderRadius: 4,
                backgroundColor: alive ? "#10B981" : "#EF4444",
              }} />
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 12, fontWeight: "600", color: colors.foreground }}>
                  {n.label || n.hostname || n.node_id.slice(0, 12)}
                  {isLeader && <Text style={{ color: "#F59E0B" }}> 👑</Text>}
                </Text>
                {n.url && <Text style={{ fontSize: 10, color: colors.mutedForeground }} numberOfLines={1}>{n.url}</Text>}
              </View>
              {latency > 0 && (
                <Text style={{ fontSize: 10, fontWeight: "700", color: latColor }}>{latency}ms</Text>
              )}
              {!isLeader && (
                <Pressable onPress={() => handleRemove(n.node_id)} hitSlop={8}>
                  <Feather name="trash-2" size={14} color={`${colors.destructive}88`} />
                </Pressable>
              )}
            </View>
          );
        })}

        {/* Add server form */}
        <View style={{ marginTop: 14, gap: 8 }}>
          <Text style={{ fontSize: 11, fontWeight: "700", color: colors.mutedForeground }}>إضافة سيرفر خارجي</Text>
          <TextInput
            value={addUrl}
            onChangeText={setAddUrl}
            placeholder="https://my-bot.render.com"
            placeholderTextColor={colors.mutedForeground}
            style={[{ height: 40, borderRadius: 10, borderWidth: 1, paddingHorizontal: 12, fontSize: 13, color: colors.foreground, borderColor: colors.border, backgroundColor: colors.muted }]}
            autoCapitalize="none"
            keyboardType="url"
          />
          <TextInput
            value={addLabel}
            onChangeText={setAddLabel}
            placeholder="اسم السيرفر (اختياري)"
            placeholderTextColor={colors.mutedForeground}
            style={[{ height: 38, borderRadius: 10, borderWidth: 1, paddingHorizontal: 12, fontSize: 13, color: colors.foreground, borderColor: colors.border, backgroundColor: colors.muted }]}
          />
          <Pressable
            onPress={handleAdd}
            disabled={adding || !addUrl.trim()}
            style={{
              height: 42, borderRadius: 10, alignItems: "center", justifyContent: "center",
              backgroundColor: adding || !addUrl.trim() ? colors.muted : "#6366F1",
              flexDirection: "row", gap: 8,
            }}
          >
            {adding ? <ActivityIndicator size="small" color="#fff" /> : (
              <>
                <Feather name="plus-circle" size={15} color="#fff" />
                <Text style={{ fontSize: 14, fontWeight: "700", color: "#fff" }}>اتصال وإضافة</Text>
              </>
            )}
          </Pressable>
          {!!msg && (
            <Text style={{ fontSize: 12, color: msg.startsWith("✅") ? "#10B981" : "#EF4444", textAlign: "center" }}>
              {msg}
            </Text>
          )}
          <Text style={{ fontSize: 10, color: colors.mutedForeground, textAlign: "center", lineHeight: 16 }}>
            يمكنك إضافة أي نسخة من السيرفر (Render / Railway / Fly.io) لتوزيع الحمل وزيادة السرعة
          </Text>
        </View>
      </View>
    </View>
  );
}

// ─── Main Settings Screen ─────────────────────────────────────────────────────

export default function SettingsScreen() {
  const colors  = useColors();
  const insets  = useSafeAreaInsets();
  const { status, settings, setMode, updateSettings } = useBotContext();
  const notify  = useNotify();

  const [isSaving,       setIsSaving]       = useState(false);
  const [pendingMode,    setPendingMode]     = useState<"demo" | "live" | null>(null);
  const [notifTesting,   setNotifTesting]   = useState(false);
  const [notifMsg,       setNotifMsg]       = useState("");
  const [isSwitching,  setIsSwitching]  = useState(false);
  const [savedFlash,   setSavedFlash]   = useState(false);

  const isLive  = status?.mode === "live";
  const topPad  = Platform.OS === "web" ? 67 : insets.top;
  const botPad  = Platform.OS === "web" ? 34 : insets.bottom;

  const handleModeToggle = () => setPendingMode(isLive ? "demo" : "live");
  const cancelModeSwitch = () => setPendingMode(null);

  const confirmModeSwitch = async () => {
    if (!pendingMode || isSwitching) return;
    setIsSwitching(true);
    try {
      if (pendingMode === "live") {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
      } else {
        Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
      }
      await setMode(pendingMode);
    } finally {
      setIsSwitching(false);
      setPendingMode(null);
    }
  };

  const handleSave = async () => {
    setIsSaving(true);
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    await updateSettings(settings);
    setIsSaving(false);
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    setSavedFlash(true);
    setTimeout(() => setSavedFlash(false), 2200);
  };

  const handleTestNotification = async () => {
    if (notifTesting) return;
    setNotifTesting(true);
    setNotifMsg("");
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);

    // Show in-app demo banners sequence
    notify("win",       "✅ ربح — BTC",         "PnL: $+4.2000 USDT | السعر: $68,200");
    setTimeout(() => notify("signal", "📊 إشارة شراء — SOL", "ثقة: 82% | SL: $140.00 | TP: $155.00"), 1200);
    setTimeout(() => notify("alert",  "⚠️ مثال تنبيه",       "هذا مثال على تنبيه انخفاض"), 2400);

    // Also ping backend push test
    try {
      const r = await fetch(`${getApiBase()}/push/test`, { method: "POST" });
      const d = await safeJson(r);
      if (d?.sent > 0)   setNotifMsg(`✅ أُرسل لـ ${d.sent} جهاز`);
      else if (d?.note)  setNotifMsg("📱 لا يوجد جهاز مسجّل");
      else               setNotifMsg("📱 الإشعار الداخلي يعمل ✓");
    } catch {
      setNotifMsg("📱 الإشعار الداخلي يعمل ✓");
    }

    setNotifTesting(false);
    setTimeout(() => setNotifMsg(""), 4000);
  };

  return (
    <ScrollView
      style={[s.root, { backgroundColor: colors.background }]}
      contentContainerStyle={{ paddingBottom: botPad + 100 }}
      showsVerticalScrollIndicator={false}
      keyboardShouldPersistTaps="handled"
    >
      {/* ── Header ── */}
      <View style={[s.header, { paddingTop: topPad + 8, borderBottomColor: colors.border }]}>
        <Text style={[s.title, { color: colors.foreground }]}>إعدادات</Text>
        {status && (
          <View style={[s.modeBadge, {
            backgroundColor: isLive ? `${colors.destructive}18` : `${colors.primary}18`,
          }]}>
            <View style={[s.modeDot, { backgroundColor: isLive ? colors.destructive : colors.primary }]} />
            <Text style={[s.modeTxt, { color: isLive ? colors.destructive : colors.primary }]}>
              {isLive ? "LIVE" : "DEMO"}
            </Text>
          </View>
        )}
      </View>

      {/* ══ SECTION 0: رابط الخادم ══ */}
      <View style={s.section}>
        <SectionHeader
          title="رابط الخادم"
          subtitle="الصق رابط الـ backend هنا — مثال: my-bot.onrender.com أو رابط Replit"
        />
        <View style={[s.card, { borderColor: colors.border }]}>
          <ServerUrlSection />
        </View>
      </View>

      {/* ══ SECTION 1: AI Provider ══ */}
      <View style={s.section}>
        <SectionHeader
          title="AI PROVIDER"
          subtitle="أضف مفتاح Gemini أو ChatGPT أو Claude لتفعيل المساعد الذكي"
        />
        <View style={[s.card, { borderColor: colors.border }]}>
          <AIProviderSection />
        </View>
      </View>

      {/* ══ SECTION 2: DEX / بلوكشين ══ */}
      <View style={s.section}>
        <SectionHeader
          title="DEX — بلوكشين مباشر"
          subtitle="المسار الرئيسي الحلال — Uniswap v3 / PancakeSwap على Base أو Polygon أو BSC"
        />
        <View style={[s.card, { borderColor: colors.border }]}>
          <DexSection />
        </View>
      </View>

      {/* ══ SECTION 3: Exchange API (CEX احتياطي) ══ */}
      <View style={s.section}>
        <SectionHeader
          title="CEX — منصة مركزية (احتياطي)"
          subtitle="MEXC أو غيرها — يُستخدم عند ضعف سيولة DEX أو سعر أفضل"
        />
        <View style={[s.card, { borderColor: colors.border }]}>
          <ExchangeSection />
        </View>
      </View>

      {/* ══ SECTION 3: وضع التداول ══ */}
      <View style={s.section}>
        <SectionHeader title="وضع التداول" />
        <View style={[s.card, { borderColor: colors.border }]}>

          {/* Mode toggle row */}
          <View style={[s.row, { borderBottomColor: colors.border, borderBottomWidth: pendingMode ? 0 : 1 }]}>
            <View style={s.rowLeft}>
              <View style={[s.rowIcon, { backgroundColor: isLive ? `${colors.destructive}18` : `${colors.primary}18` }]}>
                <Feather name={isLive ? "alert-triangle" : "shield"} size={15} color={isLive ? colors.destructive : colors.primary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={[s.rowLabel, { color: colors.foreground }]}>
                  {isLive ? "LIVE — أموال حقيقية" : "DEMO — تداول ورقي"}
                </Text>
                <Text style={[s.rowDesc, { color: colors.mutedForeground }]}>
                  {isLive
                    ? "أوامر حقيقية على حساب KuCoin"
                    : "$1,000 USDT وهمية — أسعار حقيقية من KuCoin"}
                </Text>
              </View>
            </View>
            <Switch
              value={isLive}
              onValueChange={handleModeToggle}
              trackColor={{ false: colors.muted, true: `${colors.destructive}77` }}
              thumbColor={isLive ? colors.destructive : colors.mutedForeground}
            />
          </View>

          {/* Confirmation panel */}
          {pendingMode && (
            <View style={[s.confirmPanel, {
              backgroundColor: pendingMode === "live" ? `${colors.destructive}0D` : `${colors.primary}0D`,
              borderTopColor:  pendingMode === "live" ? `${colors.destructive}33` : `${colors.primary}28`,
            }]}>
              <View style={s.confirmRow}>
                <Feather
                  name={pendingMode === "live" ? "alert-triangle" : "shield"}
                  size={16}
                  color={pendingMode === "live" ? colors.destructive : colors.primary}
                />
                <Text style={[s.confirmTitle, { color: pendingMode === "live" ? colors.destructive : colors.foreground }]}>
                  {pendingMode === "live" ? "تحويل لوضع LIVE؟" : "تحويل لوضع Demo؟"}
                </Text>
              </View>
              <Text style={[s.confirmDesc, { color: colors.mutedForeground }]}>
                {pendingMode === "live"
                  ? "ستُنفّذ أوامر حقيقية بأموالك الفعلية على KuCoin. تأكد من إضافة الـ API Keys أولاً."
                  : "تداول ورقي بـ $1,000 وهمية. لا مخاطرة بأموال حقيقية. سيتوقف البوت ويحتاج إعادة تشغيل."}
              </Text>
              <View style={s.confirmBtns}>
                <Pressable onPress={cancelModeSwitch} style={[s.confirmBtn, { backgroundColor: colors.muted, flex: 1 }]}>
                  <Text style={[s.confirmBtnTxt, { color: colors.mutedForeground }]}>إلغاء</Text>
                </Pressable>
                <Pressable
                  onPress={confirmModeSwitch}
                  disabled={isSwitching}
                  style={[s.confirmBtn, {
                    backgroundColor: pendingMode === "live" ? colors.destructive : colors.primary,
                    flex: 1, opacity: isSwitching ? 0.6 : 1,
                  }]}
                >
                  <Text style={[s.confirmBtnTxt, { color: "#fff" }]}>
                    {isSwitching ? "جارٍ التحويل..." : pendingMode === "live" ? "تأكيد LIVE" : "تأكيد Demo"}
                  </Text>
                </Pressable>
              </View>
            </View>
          )}
        </View>
      </View>

      {/* ══ SECTION 3: هدف الأداء ══ */}
      <View style={s.section}>
        <SectionHeader title="هدف الأداء" />
        <View style={[s.card, { borderColor: colors.border, padding: 20 }]}>
          <SliderInput
            label="نسبة الفوز المستهدفة"
            value={settings.targetWinRate}
            min={50} max={90} step={5} suffix="%"
            onValueChange={v => updateSettings({ targetWinRate: Math.round(v) })}
          />
          <InfoBox
            icon="zap"
            color={colors.primary}
            text="المحرّك التكيّفي يُعدّل عتبة الثقة تلقائياً لتحقيق هذا الهدف."
          />
        </View>
      </View>

      {/* ══ SECTION 4: إدارة المخاطر ══ */}
      <View style={s.section}>
        <SectionHeader title="إدارة المخاطر" />
        <View style={[s.card, { borderColor: colors.border, padding: 20 }]}>
          <SliderInput
            label="أقصى مخاطرة لكل صفقة"
            value={settings.maxRiskPercent}
            min={0.5} max={3} step={0.1} suffix="%"
            onValueChange={v => updateSettings({ maxRiskPercent: parseFloat(v.toFixed(1)) })}
          />
          <SliderInput
            label="أدنى ثقة للـ AI"
            value={settings.minConfidenceScore}
            min={60} max={90} step={5} suffix="%"
            onValueChange={v => updateSettings({ minConfidenceScore: Math.round(v) })}
          />
          <InfoBox
            icon="info"
            color={colors.warning ?? "#FF9F43"}
            text="المحرّك التكيّفي قد يُعدّل عتبة الثقة تلقائياً لتحقيق نسبة الفوز المستهدفة."
          />
        </View>
      </View>

      {/* ══ SECTION 5: الإشعارات ══ */}
      <View style={s.section}>
        <SectionHeader
          title="الإشعارات"
          subtitle="تنبيهات فورية للصفقات والأحداث المهمة"
        />
        <View style={[s.card, { borderColor: colors.border, backgroundColor: colors.card }]}>

          {/* Events list */}
          {[
            { icon: "trending-up",    color: "#00D26A", label: "صفقة رابحة (TP)", desc: "عند إغلاق صفقة بربح" },
            { icon: "trending-down",  color: "#FF6B6B", label: "Stop Loss",       desc: "عند تفعيل وقف الخسارة" },
            { icon: "zap",            color: "#00D4FF", label: "إشارة شراء جديدة", desc: "عند فتح صفقة جديدة" },
            { icon: "alert-triangle", color: "#FF9F43", label: "تنبيه انخفاض",    desc: "3+ خسائر متتالية" },
            { icon: "shield-off",     color: "#FF4757", label: "إيقاف طارئ",      desc: "5+ خسائر — توقف آمن" },
            { icon: "award",          color: "#A78BFA", label: "سلسلة فوز",       desc: "5+ صفقات رابحة متتالية" },
          ].map(ev => (
            <View key={ev.label} style={[s.row, { paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: `${colors.border}50` }]}>
              <View style={s.rowLeft}>
                <View style={[s.rowIcon, { backgroundColor: `${ev.color}18` }]}>
                  <Feather name={ev.icon as any} size={16} color={ev.color} />
                </View>
                <View>
                  <Text style={[s.rowLabel, { color: colors.foreground, fontSize: 13 }]}>{ev.label}</Text>
                  <Text style={[s.rowDesc,  { color: colors.mutedForeground }]}>{ev.desc}</Text>
                </View>
              </View>
              <View style={[ns.activeBadge, { backgroundColor: `#00D26A18`, borderColor: `#00D26A40` }]}>
                <Text style={[ns.activeTxt, { color: "#00D26A" }]}>فعّال</Text>
              </View>
            </View>
          ))}

          {/* Test button */}
          <Pressable
            onPress={handleTestNotification}
            disabled={notifTesting}
            style={[ns.testBtn, {
              backgroundColor: notifTesting ? `${colors.primary}40` : `${colors.primary}18`,
              borderColor: `${colors.primary}40`,
            }]}
          >
            {notifTesting
              ? <ActivityIndicator size="small" color={colors.primary} />
              : <Feather name="bell" size={16} color={colors.primary} />
            }
            <Text style={[ns.testTxt, { color: colors.primary }]}>
              {notifTesting ? "جارٍ الاختبار..." : "اختبر الإشعارات"}
            </Text>
          </Pressable>

          {notifMsg ? (
            <Text style={[ns.msg, { color: colors.mutedForeground }]}>{notifMsg}</Text>
          ) : null}

          <InfoBox
            icon="info"
            color={colors.primary}
            text="الإشعارات تظهر داخل التطبيق فوراً عبر WebSocket. لإشعارات في الخلفية، ثبّت التطبيق من EAS Build."
          />
        </View>
      </View>

      {/* ══ SECTION 6: الامتثال الشرعي ══ */}
      <View style={s.section}>
        <View style={[s.complianceCard, { backgroundColor: `${colors.primary}0C`, borderColor: `${colors.primary}28` }]}>
          <View style={s.complianceHeader}>
            <Feather name="check-circle" size={18} color={colors.primary} />
            <Text style={[s.complianceTitle, { color: colors.primary }]}>متوافق مع الشريعة الإسلامية</Text>
          </View>
          {[
            "تداول فوري فقط — ملكية فعلية للأصول",
            "العقود الآجلة والهامش والرافعة محظورة نهائياً",
            "أقصى مخاطرة 1.5% لكل صفقة (قابل للتعديل، حد أقصى 3%)",
            "Gemini AI مُدرَّب على مبادئ التداول الحلال",
            "تعلم من أكثر من 300 درس ونمط تداول",
          ].map(item => (
            <View key={item} style={s.complianceLine}>
              <Feather name="check" size={12} color={`${colors.primary}99`} />
              <Text style={[s.complianceTxt, { color: colors.mutedForeground }]}>{item}</Text>
            </View>
          ))}
        </View>
      </View>

      {/* ══ Save button ══ */}
      <View style={[s.section, { paddingHorizontal: 16 }]}>
        <Pressable
          onPress={handleSave}
          disabled={isSaving || savedFlash}
          style={[s.saveBtn, {
            backgroundColor: savedFlash ? `${colors.primary}99` : isSaving ? colors.muted : colors.primary,
          }]}
        >
          <Feather name={savedFlash ? "check" : "save"} size={18} color={isSaving ? colors.mutedForeground : "#fff"} />
          <Text style={[s.saveBtnTxt, { color: isSaving ? colors.mutedForeground : "#fff" }]}>
            {savedFlash ? "تم الحفظ ✓" : isSaving ? "جارٍ الحفظ..." : "حفظ وتطبيق"}
          </Text>
        </Pressable>
      </View>

      {/* ══ Database URL Section ══ */}
      <View style={s.section}>
        <SectionHeader
          title="قاعدة البيانات"
          subtitle="اربط قاعدة بيانات خارجية (Neon / Supabase / Railway) أو اترك الافتراضية"
        />
        <DatabaseUrlPanel />
      </View>

      {/* ══ Server Pool ══ */}
      <ServerPoolPanel />

      {/* ══ Logout button ══ */}
      <View style={[s.section, { paddingHorizontal: 16, paddingBottom: 40 }]}>
        <Pressable
          onPress={() => {
            Alert.alert("تسجيل الخروج", "هل تريد تسجيل الخروج من التطبيق؟", [
              { text: "إلغاء", style: "cancel" },
              {
                text: "خروج",
                style: "destructive",
                onPress: async () => {
                  await AsyncStorage.removeItem("auth_session_v1");
                  router.replace("/login");
                },
              },
            ]);
          }}
          style={[s.saveBtn, { backgroundColor: `${colors.destructive}18`, borderWidth: 1, borderColor: `${colors.destructive}44` }]}
        >
          <Feather name="log-out" size={18} color={colors.destructive} />
          <Text style={[s.saveBtnTxt, { color: colors.destructive }]}>تسجيل الخروج</Text>
        </Pressable>
      </View>
    </ScrollView>
  );
}

const s = StyleSheet.create({
  root:   { flex: 1 },
  header: {
    paddingHorizontal: 20, paddingBottom: 14, borderBottomWidth: 1,
    flexDirection: "row", alignItems: "flex-end", justifyContent: "space-between",
  },
  title:    { fontSize: 24, fontWeight: "800", letterSpacing: -0.5 },
  modeBadge: { flexDirection: "row", alignItems: "center", gap: 5, paddingHorizontal: 9, paddingVertical: 4, borderRadius: 8 },
  modeDot:   { width: 6, height: 6, borderRadius: 3 },
  modeTxt:   { fontSize: 11, fontWeight: "700", letterSpacing: 0.5 },

  section: { marginTop: 22 },

  card: { marginHorizontal: 16, borderRadius: 14, borderWidth: 1, overflow: "hidden", padding: 16 },

  row:     { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: 4 },
  rowLeft: { flexDirection: "row", alignItems: "center", gap: 12, flex: 1 },
  rowIcon: { width: 34, height: 34, borderRadius: 9, alignItems: "center", justifyContent: "center" },
  rowLabel: { fontSize: 14, fontWeight: "600" },
  rowDesc:  { fontSize: 11, marginTop: 2, lineHeight: 16 },

  confirmPanel: { borderTopWidth: 1, padding: 16, gap: 10, marginTop: 8 },
  confirmRow:   { flexDirection: "row", alignItems: "center", gap: 8 },
  confirmTitle: { fontSize: 14, fontWeight: "700", flex: 1 },
  confirmDesc:  { fontSize: 12, lineHeight: 18 },
  confirmBtns:  { flexDirection: "row", gap: 10, marginTop: 4 },
  confirmBtn:   { height: 40, borderRadius: 10, alignItems: "center", justifyContent: "center", paddingHorizontal: 14 },
  confirmBtnTxt: { fontSize: 13, fontWeight: "700" },

  complianceCard:   { marginHorizontal: 16, borderRadius: 14, borderWidth: 1, padding: 16 },
  complianceHeader: { flexDirection: "row", alignItems: "center", gap: 8, marginBottom: 12 },
  complianceTitle:  { fontSize: 15, fontWeight: "700" },
  complianceLine:   { flexDirection: "row", gap: 8, alignItems: "flex-start", marginBottom: 6 },
  complianceTxt:    { fontSize: 13, flex: 1, lineHeight: 18 },

  saveBtn:    { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 10, height: 52, borderRadius: 14 },
  saveBtnTxt: { fontSize: 16, fontWeight: "700" },
});

const ns = StyleSheet.create({
  activeBadge: { paddingHorizontal: 9, paddingVertical: 3, borderRadius: 8, borderWidth: 1 },
  activeTxt:   { fontSize: 10, fontWeight: "700", letterSpacing: 0.3 },
  testBtn:     { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 10, height: 44, borderRadius: 12, borderWidth: 1, marginTop: 14 },
  testTxt:     { fontSize: 14, fontWeight: "700" },
  msg:         { textAlign: "center", fontSize: 12, marginTop: 8 },
});
