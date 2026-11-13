/**
 * Audit: find every t("key", ...) literal used in the frontend that has no
 * entry in the locale files, and every locale key that is never used.
 */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "frontend", "src");
const LOCALES = ["en", "hi", "kn", "te", "ta"];

function walk(dir, out = []) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, out);
    else if (/\.(jsx?|tsx?)$/.test(e.name)) out.push(p);
  }
  return out;
}

const used = new Map(); // key -> Set(files)
for (const file of walk(ROOT)) {
  const src = fs.readFileSync(file, "utf8");
  const rel = path.relative(ROOT, file).replace(/\\/g, "/");
  // t("key"  and  t('key'
  const re = /\bt\(\s*["']([A-Za-z0-9_.\-]+)["']/g;
  let m;
  while ((m = re.exec(src))) {
    const key = m[1];
    if (!used.has(key)) used.set(key, new Set());
    used.get(key).add(rel);
  }
  // dynamic: t(`prefix.${x}`) — record the prefix
  const re2 = /\bt\(\s*`([^`$]+)\$\{/g;
  while ((m = re2.exec(src))) {
    const key = m[1];
    if (!used.has(key)) used.set(key, new Set());
    used.get(key).add(rel + " (dynamic)");
  }
}

const dicts = {};
for (const loc of LOCALES) {
  dicts[loc] = JSON.parse(fs.readFileSync(path.join(ROOT, "locales", `${loc}.json`), "utf8"));
}

const en = dicts.en;
const missing = [];
for (const [key, files] of used) {
  if (key.endsWith(".")) continue; // dynamic prefix
  if (!(key in en)) missing.push({ key, files: [...files].join(", ") });
}
missing.sort((a, b) => a.key.localeCompare(b.key));

console.log("=== MISSING FROM en.json (" + missing.length + ") ===");
for (const m of missing) console.log(`  ${m.key}   <- ${m.files}`);

const unused = Object.keys(en).filter((k) => !used.has(k));
console.log("\n=== DEFINED BUT NOT FOUND IN A t() CALL (" + unused.length + ") ===");
for (const k of unused) console.log("  " + k);

// key parity across locales
const enKeys = Object.keys(en).sort();
for (const loc of LOCALES) {
  const k = Object.keys(dicts[loc]).sort();
  const missingHere = enKeys.filter((x) => !k.includes(x));
  const extraHere = k.filter((x) => !enKeys.includes(x));
  if (missingHere.length || extraHere.length) {
    console.log(`\n=== ${loc} PARITY === missing: ${missingHere.join(", ") || "-"} | extra: ${extraHere.join(", ") || "-"}`);
  }
}
console.log("\nen.json key count:", enKeys.length);
