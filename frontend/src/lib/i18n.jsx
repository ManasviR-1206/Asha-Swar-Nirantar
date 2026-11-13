/* App-wide internationalisation.
 *
 * - Language is persisted in localStorage ("asn_lang") and survives
 *   navigation and refreshes. It is the UI language only — the voice
 *   language is chosen separately in the voice/visit screens.
 * - t(key) falls back to English, then to the key itself.
 */
import React, { createContext, useContext, useEffect, useMemo, useState } from "react";

import en from "../locales/en.json";
import kn from "../locales/kn.json";
import hi from "../locales/hi.json";
import te from "../locales/te.json";
import ta from "../locales/ta.json";

const DICTS = { en, kn, hi, te, ta };
export const LANG_CODES = ["en", "kn", "hi", "te", "ta"];

const I18nCtx = createContext({ lang: "en", setLang: () => {}, t: (k) => k });

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
      const v = dict[key] ?? en[key] ?? fallback;
      return v ?? key;
    };
    return { lang, setLang, t };
  }, [lang]);

  return <I18nCtx.Provider value={value}>{children}</I18nCtx.Provider>;
}

export function useI18n() {
  return useContext(I18nCtx);
}
