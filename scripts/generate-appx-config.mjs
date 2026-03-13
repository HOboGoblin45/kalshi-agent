import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const envPath = path.join(root, ".store.env");

function loadEnvFile(filePath) {
  if (!fs.existsSync(filePath)) return;
  const text = fs.readFileSync(filePath, "utf8");
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const idx = line.indexOf("=");
    if (idx <= 0) continue;
    const key = line.slice(0, idx).trim();
    let val = line.slice(idx + 1).trim();
    if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
      val = val.slice(1, -1);
    }
    if (!process.env[key]) process.env[key] = val;
  }
}

loadEnvFile(envPath);

const required = {
  APPX_PUBLISHER: "AppX publisher, e.g. CN=...",
  APPX_PUBLISHER_DISPLAY_NAME: "Publisher display name",
  APPX_IDENTITY_NAME: "Partner Center identity name",
  APPX_APPLICATION_ID: "AppX application id",
  APPX_DISPLAY_NAME: "Store display name",
};

const missing = Object.entries(required).filter(([k]) => !process.env[k]);
if (missing.length > 0) {
  const msg = missing.map(([k, d]) => `- ${k}: ${d}`).join("\n");
  console.error("Missing store metadata values. Set env vars or .store.env:\n" + msg);
  process.exit(1);
}

const packageJsonPath = path.join(root, "package.json");
const pkg = JSON.parse(fs.readFileSync(packageJsonPath, "utf8"));

const generated = {
  ...pkg.build,
  appx: {
    ...(pkg.build?.appx || {}),
    publisher: process.env.APPX_PUBLISHER,
    publisherDisplayName: process.env.APPX_PUBLISHER_DISPLAY_NAME,
    identityName: process.env.APPX_IDENTITY_NAME,
    applicationId: process.env.APPX_APPLICATION_ID,
    displayName: process.env.APPX_DISPLAY_NAME,
  },
};

const outDir = path.join(root, "build");
if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true });
const outPath = path.join(outDir, "appx.generated.json");
fs.writeFileSync(outPath, JSON.stringify(generated, null, 2) + "\n", "utf8");
console.log(`Generated ${path.relative(root, outPath)}`);
