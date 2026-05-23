import AsyncStorage from "@react-native-async-storage/async-storage";
import { Redirect } from "expo-router";
import { useEffect, useState } from "react";
import { ActivityIndicator, Text, View } from "react-native";

import { autoDiscoverServer, loadServerDomain } from "@/constants/api";

const AUTH_KEY = "auth_session_v1";

export default function Index() {
  const [checked, setChecked] = useState(false);
  const [authed, setAuthed] = useState(false);
  const [discovering, setDiscovering] = useState(true);

  useEffect(() => {
    async function init() {
      await loadServerDomain();

      setDiscovering(true);
      await autoDiscoverServer();
      setDiscovering(false);

      const v = await AsyncStorage.getItem(AUTH_KEY);
      setAuthed(v === "1");
      setChecked(true);
    }
    init();
  }, []);

  if (!checked) {
    return (
      <View
        style={{
          flex: 1,
          backgroundColor: "#0A0A0A",
          justifyContent: "center",
          alignItems: "center",
          gap: 14,
        }}
      >
        <ActivityIndicator size="large" color="#00C853" />
        {discovering && (
          <Text
            style={{
              color: "#00C853",
              fontSize: 12,
              fontFamily: "monospace",
              opacity: 0.7,
            }}
          >
            Connecting to server...
          </Text>
        )}
      </View>
    );
  }

  return <Redirect href={authed ? "/(tabs)" : "/login"} />;
}
