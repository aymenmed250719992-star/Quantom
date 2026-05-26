#!/usr/bin/env node
/**
 * update-eas-domain.js
 *
 * Reads the server domain from the environment and writes it into every build
 * profile inside eas.json before running `eas build`.
 *
 * Priority order:
 *   1. EAS_SERVER_DOMAIN  (explicit override — use this in CI)
 *   2. EXPO_PUBLIC_DOMAIN (standard Expo env var already used by the app)
 *   3. REPLIT_DEV_DOMAIN  (auto-detected inside Replit workspace)
 *
 * Usage:
 *   node scripts/update-eas-domain.js
 *   node scripts/update-eas-domain.js --domain my-bot.onrender.com
 *
 * Or just run:
 *   pnpm build:apk                  (chains this script → eas build)
 */

const fs   = require("fs");
const path = require("path");

const EAS_JSON = path.resolve(__dirname, "..", "eas.json");

function stripProtocol(raw) {
  return raw.trim().replace(/^https?:\/\//i, "").replace(/\/+$/, "");
}

function getDomain() {
  const args = process.argv.slice(2);
  const flagIdx = args.indexOf("--domain");
  if (flagIdx !== -1 && args[flagIdx + 1]) {
    return stripProtocol(args[flagIdx + 1]);
  }

  const envSources = [
    process.env.EAS_SERVER_DOMAIN,
    process.env.EXPO_PUBLIC_DOMAIN,
    process.env.REPLIT_DEV_DOMAIN,
  ];

  for (const val of envSources) {
    if (val && val.trim().length > 4) {
      return stripProtocol(val);
    }
  }

  return null;
}

function main() {
  const domain = getDomain();

  if (!domain) {
    console.error(
      "\n❌  No server domain found.\n" +
      "    Set one of these environment variables before building:\n" +
      "      EAS_SERVER_DOMAIN=my-bot.onrender.com\n" +
      "      EXPO_PUBLIC_DOMAIN=my-bot.onrender.com\n" +
      "    Or pass it directly:\n" +
      "      node scripts/update-eas-domain.js --domain my-bot.onrender.com\n",
    );
    process.exit(1);
  }

  const eas = JSON.parse(fs.readFileSync(EAS_JSON, "utf-8"));

  let updated = 0;
  for (const [profileName, profile] of Object.entries(eas.build ?? {})) {
    if (typeof profile === "object" && profile !== null) {
      profile.env = profile.env ?? {};
      const old = profile.env.EXPO_PUBLIC_DOMAIN ?? "(empty)";
      profile.env.EXPO_PUBLIC_DOMAIN = domain;
      console.log(
        `  ✅  [${profileName}]  ${old}  →  ${domain}`,
      );
      updated++;
    }
  }

  if (updated === 0) {
    console.warn("⚠️  No build profiles found in eas.json — nothing updated.");
  } else {
    fs.writeFileSync(EAS_JSON, JSON.stringify(eas, null, 2) + "\n");
    console.log(`\n🚀  eas.json updated (${updated} profile${updated > 1 ? "s" : ""})`);
    console.log(`    EXPO_PUBLIC_DOMAIN = ${domain}\n`);
  }
}

main();
