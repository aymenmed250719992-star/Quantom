import { Feather } from "@expo/vector-icons";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { router } from "expo-router";
import React, { useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Animated,
  Easing,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

const APP_EMAIL    = "aymenmed25071999@gmail.com";
const PASS_HASH    = "8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918"; // admin
const AUTH_KEY     = "auth_session_v1";

// Pure-JS SHA-256 — works in React Native / Expo Go (no crypto.subtle needed)
function sha256(str: string): string {
  const K = [
    0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
    0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
    0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
    0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
    0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
    0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
    0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2,
  ];
  const H = [0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];
  const rotr = (x: number, n: number) => (x >>> n) | (x << (32 - n));
  const bytes: number[] = [];
  for (let i = 0; i < str.length; i++) {
    const c = str.charCodeAt(i);
    if (c < 0x80) bytes.push(c);
    else if (c < 0x800) { bytes.push(0xc0 | (c >> 6), 0x80 | (c & 0x3f)); }
    else { bytes.push(0xe0 | (c >> 12), 0x80 | ((c >> 6) & 0x3f), 0x80 | (c & 0x3f)); }
  }
  const bitLen = bytes.length * 8;
  bytes.push(0x80);
  while ((bytes.length % 64) !== 56) bytes.push(0);
  for (let i = 7; i >= 0; i--) bytes.push((bitLen / Math.pow(2, i * 8)) & 0xff);
  for (let chunk = 0; chunk < bytes.length; chunk += 64) {
    const w = new Array(64).fill(0);
    for (let i = 0; i < 16; i++)
      w[i] = (bytes[chunk+i*4]<<24)|(bytes[chunk+i*4+1]<<16)|(bytes[chunk+i*4+2]<<8)|bytes[chunk+i*4+3];
    for (let i = 16; i < 64; i++) {
      const s0 = rotr(w[i-15],7)^rotr(w[i-15],18)^(w[i-15]>>>3);
      const s1 = rotr(w[i-2],17)^rotr(w[i-2],19)^(w[i-2]>>>10);
      w[i] = (w[i-16]+s0+w[i-7]+s1) >>> 0;
    }
    let [a,b,c,d,e,f,g,h] = H.slice(0,8);
    for (let i = 0; i < 64; i++) {
      const S1 = rotr(e,6)^rotr(e,11)^rotr(e,25);
      const ch = (e&f)^(~e&g);
      const t1 = (h+S1+ch+K[i]+w[i]) >>> 0;
      const S0 = rotr(a,2)^rotr(a,13)^rotr(a,22);
      const maj = (a&b)^(a&c)^(b&c);
      const t2 = (S0+maj) >>> 0;
      h=g; g=f; f=e; e=(d+t1)>>>0; d=c; c=b; b=a; a=(t1+t2)>>>0;
    }
    H[0]=(H[0]+a)>>>0; H[1]=(H[1]+b)>>>0; H[2]=(H[2]+c)>>>0; H[3]=(H[3]+d)>>>0;
    H[4]=(H[4]+e)>>>0; H[5]=(H[5]+f)>>>0; H[6]=(H[6]+g)>>>0; H[7]=(H[7]+h)>>>0;
  }
  return H.map(x => x.toString(16).padStart(8,"0")).join("");
}

export default function LoginScreen() {
  const insets   = useSafeAreaInsets();
  const [email,     setEmail]     = useState("");
  const [password,  setPassword]  = useState("");
  const [showPass,  setShowPass]  = useState(false);
  const [loading,   setLoading]   = useState(false);
  const [checking,  setChecking]  = useState(true);
  const [error,     setError]     = useState("");

  const fadeAnim  = useRef(new Animated.Value(0)).current;
  const slideAnim = useRef(new Animated.Value(30)).current;
  const shakeAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    AsyncStorage.getItem(AUTH_KEY).then((val) => {
      if (val === "1") {
        router.replace("/(tabs)");
      } else {
        setChecking(false);
        Animated.parallel([
          Animated.timing(fadeAnim,  { toValue: 1, duration: 600, useNativeDriver: true }),
          Animated.timing(slideAnim, { toValue: 0, duration: 600, easing: Easing.out(Easing.cubic), useNativeDriver: true }),
        ]).start();
      }
    });
  }, []);

  const shake = () => {
    Animated.sequence([
      Animated.timing(shakeAnim, { toValue: 10,  duration: 60, useNativeDriver: true }),
      Animated.timing(shakeAnim, { toValue: -10, duration: 60, useNativeDriver: true }),
      Animated.timing(shakeAnim, { toValue: 8,   duration: 60, useNativeDriver: true }),
      Animated.timing(shakeAnim, { toValue: -8,  duration: 60, useNativeDriver: true }),
      Animated.timing(shakeAnim, { toValue: 0,   duration: 60, useNativeDriver: true }),
    ]).start();
  };

  const handleLogin = async () => {
    setError("");
    if (!email.trim() || !password) {
      setError("يرجى إدخال البريد الإلكتروني وكلمة المرور.");
      shake();
      return;
    }
    setLoading(true);
    let success = false;
    try {
      const hash = sha256(password);
      if (email.trim().toLowerCase() === APP_EMAIL && hash === PASS_HASH) {
        await AsyncStorage.setItem(AUTH_KEY, "1");
        success = true;
      } else {
        setError("البريد الإلكتروني أو كلمة المرور غير صحيحة.");
        shake();
      }
    } catch (e) {
      console.error("[Login] error:", e);
      setError("حدث خطأ، حاول مجدداً.");
    } finally {
      setLoading(false);
    }
    if (success) {
      router.replace("/(tabs)");
    }
  };

  if (checking) {
    return (
      <View style={[s.root, s.center]}>
        <ActivityIndicator size="large" color="#00C853" />
      </View>
    );
  }

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={s.root}>
      <View style={[s.root, { paddingTop: insets.top + 30, paddingBottom: insets.bottom + 20 }]}>

        {/* ── Header ── */}
        <Animated.View style={[s.header, { opacity: fadeAnim, transform: [{ translateY: slideAnim }] }]}>
          <View style={s.logoWrap}>
            <Text style={s.logoAr}>☽</Text>
          </View>
          <Text style={s.appName}>Islamic Trading Bot</Text>
          <Text style={s.appSub}>روبوت التداول الإسلامي الذكي</Text>
        </Animated.View>

        {/* ── Card ── */}
        <Animated.View style={[s.card, { opacity: fadeAnim, transform: [{ translateX: shakeAnim }, { translateY: slideAnim }] }]}>
          <Text style={s.cardTitle}>تسجيل الدخول</Text>
          <Text style={s.cardSub}>Login to your account</Text>

          {/* Email */}
          <View style={s.fieldWrap}>
            <Text style={s.label}>البريد الإلكتروني</Text>
            <View style={s.inputRow}>
              <Feather name="mail" size={16} color="#666" style={s.inputIcon} />
              <TextInput
                style={s.input}
                value={email}
                onChangeText={(t) => { setEmail(t); setError(""); }}
                placeholder="example@email.com"
                placeholderTextColor="#444"
                keyboardType="email-address"
                autoCapitalize="none"
                autoComplete="email"
              />
            </View>
          </View>

          {/* Password */}
          <View style={s.fieldWrap}>
            <Text style={s.label}>كلمة المرور</Text>
            <View style={s.inputRow}>
              <Feather name="lock" size={16} color="#666" style={s.inputIcon} />
              <TextInput
                style={[s.input, { flex: 1 }]}
                value={password}
                onChangeText={(t) => { setPassword(t); setError(""); }}
                placeholder="••••••••••••"
                placeholderTextColor="#444"
                secureTextEntry={!showPass}
                autoComplete="password"
              />
              <Pressable onPress={() => setShowPass((p) => !p)} style={s.eyeBtn}>
                <Feather name={showPass ? "eye-off" : "eye"} size={16} color="#666" />
              </Pressable>
            </View>
          </View>

          {/* Error */}
          {!!error && (
            <View style={s.errorWrap}>
              <Feather name="alert-circle" size={13} color="#FF5252" />
              <Text style={s.errorText}>{error}</Text>
            </View>
          )}

          {/* Login Button */}
          <Pressable
            onPress={handleLogin}
            disabled={loading}
            style={[s.loginBtn, loading && s.loginBtnDisabled]}
          >
            {loading
              ? <ActivityIndicator size="small" color="#000" />
              : <Text style={s.loginBtnText}>دخول  ·  Login</Text>
            }
          </Pressable>
        </Animated.View>

        {/* ── Footer ── */}
        <Animated.View style={[s.footer, { opacity: fadeAnim }]}>
          <Text style={s.footerText}>🛡️ حلال بالكامل — Spot Only — No Leverage</Text>
        </Animated.View>
      </View>
    </KeyboardAvoidingView>
  );
}

const GREEN  = "#00C853";
const DARK   = "#0A0A0A";
const CARD   = "#111111";
const BORDER = "#1E1E1E";

const s = StyleSheet.create({
  root:           { flex: 1, backgroundColor: DARK },
  center:         { justifyContent: "center", alignItems: "center" },
  header:         { alignItems: "center", marginBottom: 36, paddingHorizontal: 24 },
  logoWrap:       { width: 70, height: 70, borderRadius: 35, backgroundColor: `${GREEN}18`, borderWidth: 2, borderColor: `${GREEN}44`, alignItems: "center", justifyContent: "center", marginBottom: 16 },
  logoAr:         { fontSize: 32, color: GREEN },
  appName:        { fontSize: 22, fontWeight: "700", color: "#FFF", letterSpacing: 0.5, marginBottom: 4 },
  appSub:         { fontSize: 13, color: "#666", letterSpacing: 1 },
  card:           { marginHorizontal: 20, backgroundColor: CARD, borderRadius: 20, padding: 24, borderWidth: 1, borderColor: BORDER },
  cardTitle:      { fontSize: 20, fontWeight: "700", color: "#FFF", marginBottom: 4, textAlign: "right" },
  cardSub:        { fontSize: 12, color: "#555", marginBottom: 24, textAlign: "right" },
  fieldWrap:      { marginBottom: 16 },
  label:          { fontSize: 12, color: "#888", marginBottom: 8, textAlign: "right", fontWeight: "600", letterSpacing: 0.5 },
  inputRow:       { flexDirection: "row", alignItems: "center", backgroundColor: "#0F0F0F", borderRadius: 12, borderWidth: 1, borderColor: BORDER, paddingHorizontal: 12, height: 48 },
  inputIcon:      { marginRight: 10 },
  input:          { flex: 1, color: "#FFF", fontSize: 14, fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace" },
  eyeBtn:         { padding: 4 },
  errorWrap:      { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: "#FF525215", borderRadius: 8, padding: 10, marginBottom: 16, borderWidth: 1, borderColor: "#FF525230" },
  errorText:      { flex: 1, color: "#FF5252", fontSize: 12, textAlign: "right" },
  loginBtn:       { backgroundColor: GREEN, borderRadius: 14, height: 52, alignItems: "center", justifyContent: "center", marginTop: 8 },
  loginBtnDisabled: { opacity: 0.6 },
  loginBtnText:   { fontSize: 16, fontWeight: "700", color: "#000", letterSpacing: 0.5 },
  footer:         { alignItems: "center", marginTop: "auto", paddingTop: 32 },
  footerText:     { fontSize: 11, color: "#333", letterSpacing: 0.3 },
});
