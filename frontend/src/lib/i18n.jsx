/* App-wide internationalisation.
 *
 * - Language is persisted in localStorage ("asn_lang") and survives
 *   navigation and refreshes. It is the UI language only — the voice
 *   language is chosen separately in the voice/visit screens.
 * - t(key) falls back to English, then to an explicit fallback, then to a
 *   human-readable label (never a raw technical key in the UI).
 * - Missing keys are logged in development for auditing.
 */
import React, { createContext, useContext, useEffect, useMemo, useState } from "react";

import en from "../locales/en.json";
import kn from "../locales/kn.json";
import hi from "../locales/hi.json";
import te from "../locales/te.json";
import ta from "../locales/ta.json";

const DICTS = { en, kn, hi, te, ta };
export const LANG_CODES = ["en", "kn", "hi", "te", "ta"];

const I18nCtx = createContext({ lang: "en", setLang: () => {}, t: (k, f) => f ?? k });

const _missingLogged = new Set();

function humanizeKey(key) {
  const raw = String(key ?? "").trim();
  if (!raw) return "";
  const part = raw.includes(".") ? raw.split(".").pop() : raw;
  return part
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^./, (c) => c.toUpperCase());
}

function logMissing(lang, key, resolvedBy) {
  try {
    if (typeof import.meta !== "undefined" && import.meta.env && import.meta.env.PROD) return;
  } catch {}
  const marker = `${lang}|${key}|${resolvedBy}`;
  if (_missingLogged.has(marker)) return;
  _missingLogged.add(marker);
  // eslint-disable-next-line no-console
  console.warn(`[i18n] Missing translation: lang="${lang}" key="${key}" (${resolvedBy})`);
}

function readSavedLang() {
  try {
    const saved = localStorage.getItem("asn_lang");
    if (saved && LANG_CODES.includes(saved)) return saved;
  } catch {}
  return "en";
}

export function LanguageProvider({ children }) {
  const [lang, setLangState] = useState(readSavedLang);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const value = useMemo(() => {
    const setLang = (code) => {
      if (!LANG_CODES.includes(code)) return;
      setLangState(code);
      try {
        localStorage.setItem("asn_lang", code);
      } catch {}
    };
    const dict = DICTS[lang] || en;
    const t = (key, fallback) => {
      if (key == null || key === "") return fallback ?? "";

      const inLang = Object.prototype.hasOwnProperty.call(dict, key) ? dict[key] : undefined;
      if (inLang != null && inLang !== "") return inLang;

      const inEn = Object.prototype.hasOwnProperty.call(en, key) ? en[key] : undefined;
      if (lang !== "en" && inEn != null && inEn !== "") {
        logMissing(lang, key, "fallback:en");
        return inEn;
      }

      if (fallback != null && fallback !== "") {
        logMissing(lang, key, "fallback:arg");
        return fallback;
      }

      if (inEn != null && inEn !== "") return inEn;

      logMissing(lang, key, "fallback:humanized");
      return humanizeKey(key);
    };
    return { lang, setLang, t };
  }, [lang]);

  return <I18nCtx.Provider value={value}>{children}</I18nCtx.Provider>;
}

export function useI18n() {
  return useContext(I18nCtx);
}
