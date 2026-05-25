/**
 * Company Dashboard — لوحة تحكم شركة التداول متعددة الوكلاء
 *
 * يعرض:
 * • حالة كل قسم (Gemini، MiroFish، MaxHermes، Groq، Risk، Execution)
 * • آخر نتيجة محاكاة الجماهير (CrowdSim)
 * • تدفق قرارات الشركة
 * • زر تحليل فوري
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Animated,
  Dimensions,
  Platform,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useColors } from "@/hooks/useColors";
import { getApiBase } from "@/constants/api";

const { width: SCREEN_W } = Dimensions.get("window");

// ─── Types ────────────────────────────────────────────────────────────────────

interface DeptInfo {
  name: string;
  role: string;
  icon: string;
  ai_provider: string;
  status: "idle" | "working" | "done" | "error";
  total_runs: number;
  errors: number;
  last_run_at: number | null;
  last_output: string | null;
}

interface CompanyStatus {
  company_name: string;
  departments: Record<string, DeptInfo>;
  total_decisions: number;
  last_decision: Decision | null;
  recent_decisions: Decision[];
  news_cache_age: number | null;
}

interface Decision {
  symbol?: string;
  price?: number;
  action?: string;
  confidence?: number;
  reason?: string;
  timestamp?: string;
  sl_pct?: number;
  tp_pct?: number;
  sources?: Record<string, unknown>;
}

interface CrowdResult {
  symbol?: string;
  n_traders?: number;
  bullish_pct?: number;
  bearish_pct?: number;
  neutral_pct?: number;
  crowd_signal?: string;
  fear_greed_index?: number;
  market_psychology?: string;
  whale_action?: string;
  whale_divergence?: boolean;
  dominant_personality?: string;
  recommendation?: string;
  timestamp?: number;
}

interface AnalysisResult {
  symbol: string;
  price: number;
  intelligence: Record<string, unknown>;
  crowd: CrowdResult;
  decision: Decision;
  timestamp: string;
}

// ─── Status colours ───────────────────────────────────────────────────────────

const STATUS_COLORS: Record<string, string> = {
  idle:    "#6B7280",
  working: "#F59E0B",
  done:    "#10B981",
  error:   "#EF4444",
};

const ACTION_COLORS: Record<string, string> = {
  BUY:        "#10B981",
  STRONG_BUY: "#059669",
  SELL:       "#EF4444",
  STRONG_SELL:"#DC2626",
  HOLD:       "#6B7280",
  NEUTRAL:    "#6B7280",
};

// ─── Sub-components ───────────────────────────────────────────────────────────

function SectionTitle({ title, colors }: { title: string; colors: any }) {
  return (
    <Text style={[styles.sectionTitle, { color: colors.mutedForeground }]}>
      {title}
    </Text>
  );
}

function DepartmentCard({
  deptKey,
  dept,
  colors,
}: {
  deptKey: string;
  dept: DeptInfo;
  colors: any;
}) {
  const pulseAnim = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    if (dept.status === "working") {
      Animated.loop(
        Animated.sequence([
          Animated.timing(pulseAnim, { toValue: 0.5, duration: 600, useNativeDriver: true }),
          Animated.timing(pulseAnim, { toValue: 1,   duration: 600, useNativeDriver: true }),
        ])
      ).start();
    } else {
      pulseAnim.setValue(1);
    }
  }, [dept.status]);

  const statusColor = STATUS_COLORS[dept.status] ?? "#6B7280";
  const lastRunStr = dept.last_run_at
    ? new Date(dept.last_run_at * 1000).toLocaleTimeString()
    : "—";

  return (
    <View style={[styles.deptCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
      <View style={styles.deptHeader}>
        <Text style={styles.deptIcon}>{dept.icon}</Text>
        <View style={{ flex: 1, marginLeft: 8 }}>
          <Text style={[styles.deptName, { color: colors.text }]} numberOfLines={1}>
            {dept.name}
          </Text>
          <Text style={[styles.deptRole, { color: colors.mutedForeground }]} numberOfLines={1}>
            {dept.role}
          </Text>
        </View>
        <Animated.View
          style={[
            styles.statusDot,
            { backgroundColor: statusColor, opacity: pulseAnim },
          ]}
        />
      </View>

      <View style={styles.deptMeta}>
        <View style={styles.metaChip}>
          <Text style={[styles.metaLabel, { color: colors.mutedForeground }]}>AI</Text>
          <Text style={[styles.metaValue, { color: colors.primary }]}>
            {dept.ai_provider.toUpperCase()}
          </Text>
        </View>
        <View style={styles.metaChip}>
          <Text style={[styles.metaLabel, { color: colors.mutedForeground }]}>RUNS</Text>
          <Text style={[styles.metaValue, { color: colors.text }]}>{dept.total_runs}</Text>
        </View>
        <View style={styles.metaChip}>
          <Text style={[styles.metaLabel, { color: colors.mutedForeground }]}>ERR</Text>
          <Text style={[styles.metaValue, { color: dept.errors > 0 ? "#EF4444" : colors.text }]}>
            {dept.errors}
          </Text>
        </View>
        <View style={styles.metaChip}>
          <Text style={[styles.metaLabel, { color: colors.mutedForeground }]}>TIME</Text>
          <Text style={[styles.metaValue, { color: colors.text }]}>{lastRunStr}</Text>
        </View>
      </View>

      {dept.last_output && (
        <Text style={[styles.deptOutput, { color: colors.mutedForeground }]} numberOfLines={2}>
          {dept.last_output}
        </Text>
      )}
    </View>
  );
}

function CrowdBar({ label, pct, color }: { label: string; pct: number; color: string }) {
  const barWidth = Math.min(100, Math.max(0, pct));
  return (
    <View style={styles.crowdBarRow}>
      <Text style={[styles.crowdBarLabel, { color: "#9CA3AF" }]}>{label}</Text>
      <View style={[styles.crowdBarTrack, { backgroundColor: "#1F2937" }]}>
        <View style={[styles.crowdBarFill, { width: `${barWidth}%` as any, backgroundColor: color }]} />
      </View>
      <Text style={[styles.crowdBarPct, { color }]}>{pct.toFixed(1)}%</Text>
    </View>
  );
}

function DecisionBadge({ action, confidence }: { action?: string; confidence?: number }) {
  const act = (action ?? "HOLD").toUpperCase();
  const color = ACTION_COLORS[act] ?? "#6B7280";
  return (
    <View style={[styles.decisionBadge, { backgroundColor: color + "22", borderColor: color }]}>
      <Text style={[styles.decisionAction, { color }]}>{act}</Text>
      {confidence !== undefined && (
        <Text style={[styles.decisionConf, { color }]}>{confidence}%</Text>
      )}
    </View>
  );
}

// ─── Main Screen ──────────────────────────────────────────────────────────────

export default function CompanyScreen() {
  const colors  = useColors();
  const insets  = useSafeAreaInsets();

  const [status,   setStatus]   = useState<CompanyStatus | null>(null);
  const [crowd,    setCrowd]    = useState<CrowdResult | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null);
  const [loading,  setLoading]  = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [activeTab, setActiveTab] = useState<"depts" | "crowd" | "decisions">("depts");
  const [symbol, setSymbol] = useState("BTC/USDT");

  const fetchStatus = useCallback(async () => {
    try {
      const base = getApiBase();
      const [sRes, cRes] = await Promise.all([
        fetch(`${base}/company/status`),
        fetch(`${base}/crowd/latest`),
      ]);
      if (sRes.ok) {
        const data = await sRes.json();
        setStatus(data);
      }
      if (cRes.ok) {
        const data = await cRes.json();
        setCrowd(data);
      }
    } catch (_) {}
  }, []);

  const runAnalysis = useCallback(async () => {
    setAnalyzing(true);
    try {
      const base = getApiBase();
      const res = await fetch(`${base}/company/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol, price: 0 }),
      });
      if (res.ok) {
        const data = await res.json();
        setAnalysis(data);
        setActiveTab("decisions");
        await fetchStatus();
      }
    } catch (_) {}
    setAnalyzing(false);
  }, [symbol, fetchStatus]);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await fetchStatus();
    setRefreshing(false);
  }, [fetchStatus]);

  useEffect(() => {
    fetchStatus();
    const iv = setInterval(fetchStatus, 30_000);
    return () => clearInterval(iv);
  }, [fetchStatus]);

  const deptEntries = status
    ? Object.entries(status.departments)
    : [];

  const recentDecisions = status?.recent_decisions ?? [];

  const paddingBottom = Platform.OS === "ios" ? insets.bottom + 90 : insets.bottom + 70;

  return (
    <View style={[styles.root, { backgroundColor: colors.background }]}>
      {/* ── Header ── */}
      <View style={[styles.header, { paddingTop: insets.top + 8 }]}>
        <View>
          <Text style={[styles.headerTitle, { color: colors.text }]}>🏢 QUANTOM COMPANY</Text>
          <Text style={[styles.headerSub, { color: colors.mutedForeground }]}>
            Multi-Agent Trading System
          </Text>
        </View>
        {status && (
          <View style={[styles.decisionsChip, { backgroundColor: colors.primary + "22" }]}>
            <Text style={[styles.decisionsNum, { color: colors.primary }]}>
              {status.total_decisions}
            </Text>
            <Text style={[styles.decisionsLabel, { color: colors.mutedForeground }]}>decisions</Text>
          </View>
        )}
      </View>

      {/* ── Analyze Button ── */}
      <TouchableOpacity
        style={[styles.analyzeBtn, { backgroundColor: analyzing ? "#374151" : colors.primary }]}
        onPress={runAnalysis}
        disabled={analyzing}
        activeOpacity={0.8}
      >
        {analyzing ? (
          <ActivityIndicator color="#fff" size="small" />
        ) : (
          <Text style={styles.analyzeBtnText}>⚡ تحليل شامل — {symbol}</Text>
        )}
      </TouchableOpacity>

      {/* ── Tabs ── */}
      <View style={[styles.tabBar, { backgroundColor: colors.card, borderBottomColor: colors.border }]}>
        {(["depts", "crowd", "decisions"] as const).map((t) => (
          <TouchableOpacity
            key={t}
            style={[styles.tab, activeTab === t && { borderBottomColor: colors.primary, borderBottomWidth: 2 }]}
            onPress={() => setActiveTab(t)}
          >
            <Text style={[styles.tabLabel, { color: activeTab === t ? colors.primary : colors.mutedForeground }]}>
              {t === "depts" ? "🏛 أقسام" : t === "crowd" ? "🐟 الجماهير" : "⚡ قرارات"}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* ── Content ── */}
      <ScrollView
        contentContainerStyle={{ padding: 16, paddingBottom }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
        showsVerticalScrollIndicator={false}
      >
        {/* ── DEPARTMENTS TAB ── */}
        {activeTab === "depts" && (
          <>
            <SectionTitle title="الأقسام والوكلاء النشطون" colors={colors} />
            {deptEntries.length === 0 && (
              <View style={styles.emptyState}>
                <Text style={[styles.emptyText, { color: colors.mutedForeground }]}>
                  جاري تحميل حالة الأقسام...
                </Text>
                <ActivityIndicator color={colors.primary} style={{ marginTop: 12 }} />
              </View>
            )}
            {deptEntries.map(([key, dept]) => (
              <DepartmentCard key={key} deptKey={key} dept={dept} colors={colors} />
            ))}

            {/* Company Architecture diagram */}
            <View style={[styles.archCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
              <Text style={[styles.archTitle, { color: colors.text }]}>🏗 هيكل الشركة</Text>
              <Text style={[styles.archBody, { color: colors.mutedForeground }]}>
                {"📰 Gemini → يرصد الأخبار دورياً\n" +
                 "🐟 MiroFish → يُحاكي 1000+ متداول وهمي\n" +
                 "🧠 MaxHermes → ذاكرة دائمة + تحليل Excel\n" +
                 "⚡ Groq → القرار النهائي السريع\n" +
                 "🛡️ Risk → تحقق الامتثال الشرعي\n" +
                 "🎯 Execution → تنفيذ Spot حلال فوراً"}
              </Text>
            </View>
          </>
        )}

        {/* ── CROWD TAB ── */}
        {activeTab === "crowd" && (
          <>
            <SectionTitle title={`محاكاة الجماهير (MiroFish) — ${crowd?.n_traders ?? 1000} متداول`} colors={colors} />

            {crowd ? (
              <>
                {/* Signal badge */}
                <View style={[styles.crowdSignalCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
                  <View style={styles.crowdSignalRow}>
                    <View>
                      <Text style={[styles.crowdSignalLabel, { color: colors.mutedForeground }]}>إشارة الجموع</Text>
                      <Text style={[
                        styles.crowdSignalValue,
                        { color: ACTION_COLORS[crowd.crowd_signal ?? "NEUTRAL"] ?? "#6B7280" }
                      ]}>
                        {crowd.crowd_signal ?? "—"}
                      </Text>
                    </View>
                    <View style={styles.fearGreedGauge}>
                      <Text style={[styles.fearGreedNum, {
                        color: (crowd.fear_greed_index ?? 0.5) > 0.6 ? "#10B981" : (crowd.fear_greed_index ?? 0.5) < 0.4 ? "#EF4444" : "#F59E0B"
                      }]}>
                        {Math.round((crowd.fear_greed_index ?? 0.5) * 100)}
                      </Text>
                      <Text style={[styles.fearGreedLabel, { color: colors.mutedForeground }]}>Fear/Greed</Text>
                    </View>
                  </View>
                  <Text style={[styles.crowdPsych, { color: colors.text }]}>
                    {crowd.market_psychology ?? "محايد"}
                  </Text>
                </View>

                {/* Bars */}
                <View style={[styles.barsCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
                  <CrowdBar label="🐂 صاعد" pct={crowd.bullish_pct ?? 50}  color="#10B981" />
                  <CrowdBar label="🐻 هابط" pct={crowd.bearish_pct ?? 50}  color="#EF4444" />
                  <CrowdBar label="⚪ محايد" pct={crowd.neutral_pct ?? 0}   color="#6B7280" />
                </View>

                {/* Whale */}
                <View style={[styles.whaleCard, {
                  backgroundColor: crowd.whale_divergence ? "#7C3AED22" : colors.card,
                  borderColor: crowd.whale_divergence ? "#7C3AED" : colors.border,
                }]}>
                  <Text style={[styles.whaleTitle, { color: crowd.whale_divergence ? "#7C3AED" : colors.text }]}>
                    🐳 الحيتان
                  </Text>
                  <Text style={[styles.whaleAction, {
                    color: ACTION_COLORS[(crowd.whale_action ?? "hold").toUpperCase()] ?? colors.text,
                  }]}>
                    {(crowd.whale_action ?? "HOLD").toUpperCase()}
                  </Text>
                  {crowd.whale_divergence && (
                    <Text style={styles.whaleDivergence}>
                      ⚠️ الحيتان تعمل عكس الجموع — إشارة عكسية قوية!
                    </Text>
                  )}
                </View>

                {/* Recommendation */}
                {crowd.recommendation && (
                  <View style={[styles.recCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
                    <Text style={[styles.recTitle, { color: colors.mutedForeground }]}>التفسير</Text>
                    <Text style={[styles.recBody, { color: colors.text }]}>{crowd.recommendation}</Text>
                  </View>
                )}
              </>
            ) : (
              <View style={styles.emptyState}>
                <Text style={[styles.emptyText, { color: colors.mutedForeground }]}>
                  اضغط "تحليل شامل" لتشغيل محاكاة الجماهير
                </Text>
              </View>
            )}
          </>
        )}

        {/* ── DECISIONS TAB ── */}
        {activeTab === "decisions" && (
          <>
            <SectionTitle title="قرارات الشركة الأخيرة (Groq)" colors={colors} />

            {analysis && (
              <View style={[styles.latestCard, { backgroundColor: "#111827", borderColor: colors.primary }]}>
                <View style={styles.latestHeader}>
                  <Text style={[styles.latestSymbol, { color: colors.primary }]}>
                    {analysis.symbol}
                  </Text>
                  <DecisionBadge action={analysis.decision?.action} confidence={analysis.decision?.confidence} />
                </View>
                <Text style={[styles.latestPrice, { color: colors.mutedForeground }]}>
                  ${analysis.price?.toFixed(4) ?? "—"}
                </Text>
                {analysis.decision?.reason && (
                  <Text style={[styles.latestReason, { color: colors.text }]}>
                    {analysis.decision.reason}
                  </Text>
                )}
                <View style={styles.latestSLTP}>
                  <Text style={[styles.slText, { color: "#EF4444" }]}>
                    SL {analysis.decision?.sl_pct ?? 2}%
                  </Text>
                  <Text style={[styles.tpText, { color: "#10B981" }]}>
                    TP {analysis.decision?.tp_pct ?? 4}%
                  </Text>
                </View>
                {analysis.decision?.sources && (
                  <View style={styles.sourcesRow}>
                    <Text style={[styles.sourceLabel, { color: colors.mutedForeground }]}>
                      📰 {String(analysis.decision.sources.intelligence ?? 0).slice(0, 5)}
                    </Text>
                    <Text style={[styles.sourceLabel, { color: colors.mutedForeground }]}>
                      🐟 {String(analysis.decision.sources.crowd ?? "—")}
                    </Text>
                    <Text style={[styles.sourceLabel, { color: colors.mutedForeground }]}>
                      🧠 {analysis.decision.sources.memory ? "✓ ذاكرة" : "—"}
                    </Text>
                  </View>
                )}
              </View>
            )}

            {recentDecisions.length === 0 && !analysis && (
              <View style={styles.emptyState}>
                <Text style={[styles.emptyText, { color: colors.mutedForeground }]}>
                  لا يوجد قرارات بعد — اضغط "تحليل شامل"
                </Text>
              </View>
            )}

            {recentDecisions.map((d, i) => (
              <View
                key={i}
                style={[styles.decisionCard, { backgroundColor: colors.card, borderColor: colors.border }]}
              >
                <View style={styles.decisionRow}>
                  <Text style={[styles.decSymbol, { color: colors.text }]}>{d.symbol ?? "—"}</Text>
                  <DecisionBadge action={d.action} confidence={d.confidence} />
                </View>
                {d.reason && (
                  <Text style={[styles.decReason, { color: colors.mutedForeground }]} numberOfLines={2}>
                    {d.reason}
                  </Text>
                )}
                {d.timestamp && (
                  <Text style={[styles.decTime, { color: "#4B5563" }]}>
                    {new Date(d.timestamp).toLocaleTimeString()}
                  </Text>
                )}
              </View>
            ))}

            {/* Render.com link */}
            <View style={[styles.renderCard, { backgroundColor: "#0F172A", borderColor: "#1D4ED8" }]}>
              <Text style={[styles.renderTitle, { color: "#60A5FA" }]}>
                🚀 Deploy على Render.com (مجاناً)
              </Text>
              <Text style={[styles.renderBody, { color: "#94A3B8" }]}>
                {"1. اذهب إلى: render.com/register\n" +
                 "2. New → Web Service\n" +
                 "3. Connect GitHub repo\n" +
                 "4. Root Dir: backend | Build: pip install -r requirements.txt\n" +
                 "5. Start: uvicorn main:app --host 0.0.0.0 --port $PORT\n" +
                 "6. أضف Environment Variables:\n" +
                 "   QUANTOM_DB_URL, GEMINI_API_KEY, etc."}
              </Text>
              <Text style={[styles.renderUrl, { color: "#3B82F6" }]}>
                🌐 render.com
              </Text>
            </View>
          </>
        )}
      </ScrollView>
    </View>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  root: { flex: 1 },

  header: {
    flexDirection:  "row",
    justifyContent: "space-between",
    alignItems:     "center",
    paddingHorizontal: 16,
    paddingBottom: 8,
  },
  headerTitle: { fontSize: 18, fontWeight: "800", letterSpacing: 0.5 },
  headerSub:   { fontSize: 11, marginTop: 2 },

  decisionsChip:   { borderRadius: 12, paddingHorizontal: 10, paddingVertical: 6, alignItems: "center" },
  decisionsNum:    { fontSize: 20, fontWeight: "800" },
  decisionsLabel:  { fontSize: 9, fontWeight: "600", marginTop: -2 },

  analyzeBtn: {
    marginHorizontal: 16,
    marginBottom: 8,
    borderRadius: 10,
    paddingVertical: 12,
    alignItems: "center",
  },
  analyzeBtnText: { color: "#fff", fontWeight: "700", fontSize: 14, letterSpacing: 0.5 },

  tabBar: {
    flexDirection:    "row",
    borderBottomWidth: 1,
    marginBottom: 0,
  },
  tab: { flex: 1, paddingVertical: 10, alignItems: "center" },
  tabLabel: { fontSize: 12, fontWeight: "700" },

  sectionTitle: { fontSize: 10, fontWeight: "700", letterSpacing: 1, marginBottom: 8, marginTop: 4 },

  deptCard: {
    borderRadius: 12,
    borderWidth: 1,
    padding: 12,
    marginBottom: 10,
  },
  deptHeader: { flexDirection: "row", alignItems: "center", marginBottom: 8 },
  deptIcon:   { fontSize: 22 },
  deptName:   { fontSize: 13, fontWeight: "700" },
  deptRole:   { fontSize: 10, marginTop: 1 },
  statusDot:  { width: 10, height: 10, borderRadius: 5, marginLeft: 8 },

  deptMeta: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginBottom: 6 },
  metaChip:  { alignItems: "center", minWidth: 50 },
  metaLabel: { fontSize: 8, fontWeight: "700", letterSpacing: 0.5 },
  metaValue: { fontSize: 11, fontWeight: "700" },

  deptOutput: { fontSize: 10, lineHeight: 14, marginTop: 4 },

  archCard: { borderRadius: 12, borderWidth: 1, padding: 14, marginTop: 4 },
  archTitle: { fontSize: 13, fontWeight: "700", marginBottom: 8 },
  archBody:  { fontSize: 12, lineHeight: 20 },

  // crowd
  crowdSignalCard: { borderRadius: 12, borderWidth: 1, padding: 14, marginBottom: 10 },
  crowdSignalRow:  { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 8 },
  crowdSignalLabel:{ fontSize: 10, fontWeight: "600" },
  crowdSignalValue:{ fontSize: 24, fontWeight: "800", marginTop: 2 },
  fearGreedGauge:  { alignItems: "center" },
  fearGreedNum:    { fontSize: 28, fontWeight: "800" },
  fearGreedLabel:  { fontSize: 9, fontWeight: "600" },
  crowdPsych:      { fontSize: 13, fontWeight: "600" },

  barsCard: { borderRadius: 12, borderWidth: 1, padding: 14, marginBottom: 10 },
  crowdBarRow:   { flexDirection: "row", alignItems: "center", marginBottom: 8 },
  crowdBarLabel: { width: 55, fontSize: 11, fontWeight: "600" },
  crowdBarTrack: { flex: 1, height: 8, borderRadius: 4, overflow: "hidden", marginHorizontal: 8 },
  crowdBarFill:  { height: 8, borderRadius: 4 },
  crowdBarPct:   { width: 42, textAlign: "right", fontSize: 11, fontWeight: "700" },

  whaleCard: { borderRadius: 12, borderWidth: 1, padding: 14, marginBottom: 10 },
  whaleTitle:  { fontSize: 13, fontWeight: "700", marginBottom: 4 },
  whaleAction: { fontSize: 22, fontWeight: "800", marginBottom: 4 },
  whaleDivergence: { color: "#7C3AED", fontSize: 12, fontWeight: "600", marginTop: 4 },

  recCard: { borderRadius: 12, borderWidth: 1, padding: 14, marginBottom: 10 },
  recTitle:{ fontSize: 10, fontWeight: "600", marginBottom: 4 },
  recBody: { fontSize: 13, lineHeight: 20 },

  // decisions
  latestCard: { borderRadius: 12, borderWidth: 1.5, padding: 14, marginBottom: 12 },
  latestHeader:{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 4 },
  latestSymbol:{ fontSize: 18, fontWeight: "800" },
  latestPrice: { fontSize: 12, marginBottom: 6 },
  latestReason:{ fontSize: 13, lineHeight: 20, marginBottom: 8 },
  latestSLTP:  { flexDirection: "row", gap: 12, marginBottom: 8 },
  slText:      { fontSize: 12, fontWeight: "700" },
  tpText:      { fontSize: 12, fontWeight: "700" },
  sourcesRow:  { flexDirection: "row", gap: 12 },
  sourceLabel: { fontSize: 10, fontWeight: "600" },

  decisionBadge: { flexDirection: "row", alignItems: "center", gap: 4, borderWidth: 1, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 4 },
  decisionAction:{ fontSize: 12, fontWeight: "800" },
  decisionConf:  { fontSize: 11, fontWeight: "700" },

  decisionCard: { borderRadius: 10, borderWidth: 1, padding: 10, marginBottom: 8 },
  decisionRow:  { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 4 },
  decSymbol:    { fontSize: 14, fontWeight: "700" },
  decReason:    { fontSize: 11, lineHeight: 16, marginBottom: 4 },
  decTime:      { fontSize: 9 },

  renderCard:   { borderRadius: 12, borderWidth: 1, padding: 14, marginTop: 8, marginBottom: 8 },
  renderTitle:  { fontSize: 14, fontWeight: "700", marginBottom: 8 },
  renderBody:   { fontSize: 11, lineHeight: 18, marginBottom: 8 },
  renderUrl:    { fontSize: 13, fontWeight: "700" },

  emptyState: { alignItems: "center", paddingVertical: 40 },
  emptyText:  { fontSize: 13, textAlign: "center" },
});
