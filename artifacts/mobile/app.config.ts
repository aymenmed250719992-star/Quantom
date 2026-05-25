import { ExpoConfig, ConfigContext } from "expo/config";

const PROD_DOMAIN = (process.env.EXPO_PUBLIC_DOMAIN ?? "").replace(/^https?:\/\//, "").replace(/\/+$/, "");
const PROJECT_ID = "852966ee-aec0-4e74-85a9-ee6093dd8fd7";

export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  name: "Quantom",
  slug: "islamic-trading-bot",
  version: "1.0.2",
  orientation: "portrait",
  icon: "./assets/images/icon.png",
  scheme: "quantom",
  userInterfaceStyle: "dark",
  newArchEnabled: true,
  splash: {
    image: "./assets/images/icon.png",
    resizeMode: "contain",
    backgroundColor: "#0A0A0A",
  },
  updates: {
    url: `https://u.expo.dev/${PROJECT_ID}`,
    enabled: true,
    checkAutomatically: "ON_LOAD",
    fallbackToCacheTimeout: 0,
  },
  runtimeVersion: {
    policy: "appVersion",
  },
  ios: {
    supportsTablet: false,
    bundleIdentifier: "com.quantom.app",
  },
  android: {
    adaptiveIcon: {
      foregroundImage: "./assets/images/icon.png",
      backgroundColor: "#0A0A0A",
    },
    package: "com.quantom.app",
    versionCode: 3,
    permissions: [
      "android.permission.INTERNET",
      "android.permission.ACCESS_NETWORK_STATE",
      "android.permission.VIBRATE",
    ],
  },
  web: {
    favicon: "./assets/images/icon.png",
  },
  plugins: [
    [
      "expo-router",
      {
        origin: PROD_DOMAIN ? `https://${PROD_DOMAIN}/` : "https://localhost/",
      },
    ],
    "expo-font",
    "expo-web-browser",
    "expo-updates",
  ],
  experiments: {
    typedRoutes: true,
    reactCompiler: true,
  },
  extra: {
    EXPO_PUBLIC_DOMAIN: PROD_DOMAIN,
    eas: {
      projectId: PROJECT_ID,
    },
  },
  owner: "quantom23",
});
