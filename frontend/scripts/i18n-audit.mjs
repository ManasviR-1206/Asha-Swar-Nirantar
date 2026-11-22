import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const srcDir = path.resolve(__dirname, "../src");
const localesDir = path.join(srcDir, "locales");
const langs = ["en", "kn", "hi", "te", "ta"];

function walk(dir, exts, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "node_modules" || entry.name === "dist") continue;
      walk(p, exts, out);
    } else if (exts.some((e) => p.endsWith(e))) out.push(p);
  }
  return out;
}

const dicts = Object.fromEntries(
  langs.map((l) => [l, JSON.parse(fs.readFileSync(path.join(localesDir, `${l}.json`), "utf8"))])
);

const files = walk(srcDir, [".js", ".jsx", ".ts", ".tsx"]);
const used = new Map(); // key -> [locations]
const directRe = /\bt\(\s*(["'`])([A-Za-z0-9_.:-]+)\1/g;

for (const fp of files) {
  const text = fs.readFileSync(fp, "utf8");
  const rel = path.relative(srcDir, fp).replace(/\\/g, "/");
  const lines = text.split(/\r?\n/);
  for (let i = 0; i < lines.length; i++) {
    let m;
    directRe.lastIndex = 0;
    while ((m = directRe.exec(lines[i]))) {
      const k = m[2];
      if (!used.has(k)) used.set(k, []);
      used.get(k).push(`${rel}:${i + 1}`);
    }
  }
}

// Dynamic label families (kept in sync with frontend/src/lib/labels.js and common patterns)
const dynamic = new Set();
for (const c of ["pregnancy","newborn","child","immunisation","elderly","nutrition","adolescent","community","general","household"]) dynamic.add(`cat.${c}`);
for (const c of ["anc","postnatal","newborn","vaccination","nutrition","community","household","growth","followup"]) dynamic.add(`ftype.${c}`);
for (const c of ["head","spouse","child","parent","sibling","grandparent","other"]) dynamic.add(`rel.${c}`);
for (const c of ["male","female","other","transgender"]) dynamic.add(`gender.${c}`);
for (const c of ["demoSent","delivered","failed","cancelled","sent","overdue","pending","scheduled","completed","processed","open","acknowledged"]) dynamic.add(`status.${c}`);

const considered = new Set([...used.keys(), ...dynamic]);
let failed = false;
console.log(`Languages: ${langs.join(", ")}`);
console.log(`Direct keys found: ${used.size}`);
console.log(`Dynamic/family keys considered: ${dynamic.size}`);
console.log(`Total keys checked: ${considered.size}`);
for (const lang of langs) {
  const missing = [...considered].filter((k) => !(k in dicts[lang]));
  console.log(`${lang}: ${Object.keys(dicts[lang]).length} dict keys, missing ${missing.length}`);
  if (missing.length) {
    failed = true;
    for (const k of missing) console.log(`  MISSING ${lang}: ${k}`);
  }
}
// cross-language completeness vs English
const enKeys = new Set(Object.keys(dicts.en));
for (const lang of langs.filter((l) => l !== "en")) {
  const missingVsEn = [...enKeys].filter((k) => !(k in dicts[lang]));
  if (missingVsEn.length) {
    failed = true;
    console.log(`${lang} missing vs en: ${missingVsEn.length}`);
  }
}
if (failed) {
  console.error("i18n audit failed");
  process.exit(1);
}
console.log("i18n audit passed");
