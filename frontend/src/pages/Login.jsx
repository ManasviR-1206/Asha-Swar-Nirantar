import { Suspense, lazy, useEffect, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Eye,
  EyeOff,
  Loader2,
  LogIn,
  Sparkles,
  ChevronDown,
  Info,
  Heart,
  Zap,
} from "lucide-react";
import { useAuth } from "../lib/auth.jsx";
import { LANGUAGES } from "../lib/api.js";
import { useI18n } from "../lib/i18n.jsx";

const Tara = lazy(() => import("../components/three/Tara.jsx"));

const DEMO_CREDS = { id: "ASHA001", password: "Demo@123" };

export default function Login() {
  const { login, mode } = useAuth();
  const navigate = useNavigate();
  const { t, lang, setLang } = useI18n();

  const [workerId, setWorkerId] = useState("");
  const [password, setPassword] = useState("");
  // The UI language is shared with the rest of the app; the dropdown only
  // reflects / changes it. It persists across visits via localStorage.
  const [language, setLanguage] = useState(lang || "en");
  const [remember, setRemember] = useState(true);
  const [showPassword, setShowPassword] = useState(false);
  const [focusField, setFocusField] = useState(null);
  const [busy, setBusy] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState("");
  const [touched, setTouched] = useState({});
  const [demoFilled, setDemoFilled] = useState(false);

  // Keep the dropdown in step with the persisted UI language.
  useEffect(() => {
    setLanguage(lang || "en");
  }, [lang]);

  // Tara's emotional state reacts to the form
  const taraState = busy
    ? "think"
    : success
      ? "happy"
      : focusField === "password"
        ? "cover"
        : focusField === "workerId"
          ? "idle"
          : "wave";

  const taraGaze =
    focusField === "workerId" || focusField === "password"
      ? { x: 0.85, y: -0.05 } // look toward the login card
      : null;

  const validate = (id, pwd) => {
    const errs = {};
    if (!id.trim()) errs.workerId = t("login.errEmpty");
    if (!pwd) errs.password = t("login.errEmpty");
    return errs;
  };

  const submit = async (e, override) => {
    e?.preventDefault?.();
    // `override` lets the demo button supply credentials directly — React
    // state updates are async, so reading them from the closure here would
    // still see the previous (empty) values.
    const id = override?.workerId ?? workerId;
    const pwd = override?.password ?? password;
    setTouched({ workerId: true, password: true });
    const errs = validate(id, pwd);
    if (Object.keys(errs).length) return;
    setBusy(true);
    setError("");
    try {
      await login(id.trim(), pwd, language, remember);
      setSuccess(true);
      setTimeout(() => navigate("/app"), 1400);
    } catch (err) {
      setError(err.message || t("login.errInvalid"));
      setBusy(false);
    }
  };

  /** Auto-fill the demo credentials and log in directly. */
  const tryDemo = () => {
    setWorkerId(DEMO_CREDS.id);
    setPassword(DEMO_CREDS.password);
    setDemoFilled(true);
    submit(undefined, { workerId: DEMO_CREDS.id, password: DEMO_CREDS.password });
  };

  return (
    <div
      className="min-h-screen grid md:grid-cols-2"
      style={{ background: "linear-gradient(150deg, #100C18 0%, #211329 55%, #38152E 100%)" }}
    >
      {/* ================= LEFT — Tara ================= */}
      <div className="relative hidden md:flex flex-col items-center justify-center overflow-hidden">
        {/* floating holographic circles */}
        <div className="absolute inset-0 pointer-events-none">
          {[
            { s: 340, x: "6%", y: "12%", c: "rgba(240,120,173,0.10)" },
            { s: 180, x: "70%", y: "6%", c: "rgba(183,163,255,0.12)" },
            { s: 110, x: "78%", y: "70%", c: "rgba(240,120,173,0.14)" },
            { s: 70, x: "14%", y: "76%", c: "rgba(255,255,255,0.07)" },
          ].map((c, i) => (
            <motion.div
              key={i}
              className="absolute rounded-full border"
              style={{
                width: c.s,
                height: c.s,
                left: c.x,
                top: c.y,
                borderColor: c.c,
                background: `${c.c}`,
                filter: "blur(0.5px)",
              }}
              animate={{ y: [0, -14, 0] }}
              transition={{ repeat: Infinity, duration: 5 + i, ease: "easeInOut" }}
            />
          ))}
        </div>

        <div className="relative h-[420px] w-full max-w-xl">
          <Suspense
            fallback={
              <div className="h-full flex items-center justify-center">
                <motion.div
                  animate={{ scale: [1, 1.2, 1], opacity: [0.6, 1, 0.6] }}
                  transition={{ repeat: Infinity, duration: 1.8 }}
                  className="w-16 h-16 rounded-full"
                  style={{
                    background: "radial-gradient(circle at 35% 35%, #ffd3e6, #f078ad 55%, #8755d9)",
                    boxShadow: "0 0 40px rgba(240,120,173,0.5)",
                  }}
                />
              </div>
            }
          >
            <TaraCanvas state={taraState} gaze={taraGaze} />
          </Suspense>
        </div>

        <div className="relative z-10 text-center px-8 -mt-6">
          <motion.h2
            key={taraState}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-2xl font-extrabold"
          >
            {t("login.welcome")}
          </motion.h2>
          <p className="text-white/60 text-sm mt-3 max-w-md mx-auto leading-relaxed">
            {t("login.subtitle")}
          </p>
        </div>
      </div>

      {/* ================= RIGHT — login card ================= */}
      <div className="flex items-center justify-center px-5 py-12 relative">
        <div className="absolute inset-0 pointer-events-none md:hidden flex items-end justify-center">
          <div className="h-40 w-40 opacity-40">
            <Suspense fallback={null}>
              <TaraCanvas state={taraState} gaze={null} compact />
            </Suspense>
          </div>
        </div>

        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease: "easeOut" }}
          className="relative z-10 w-full max-w-md glass-strong rounded-[2rem] p-8 sm:p-10 shadow-glass"
        >
          <div className="flex items-center justify-between mb-1">
            <div className="flex items-center gap-2">
              <span
                className="inline-block w-3 h-3 rounded-full"
                style={{
                  background: "radial-gradient(circle at 35% 35%, #ffd3e6, #f078ad 55%, #8755d9)",
                  boxShadow: "0 0 10px rgba(240,120,173,0.8)",
                }}
              />
              <span className="text-[11px] tracking-[0.2em] uppercase text-mint font-bold">
                {t("app.name")}
              </span>
            </div>
            <select
              value={language}
              onChange={(e) => {
                setLanguage(e.target.value);
                setLang(e.target.value);
              }}
              className="text-[11px] bg-white/[0.07] border border-white/10 rounded-lg px-2 py-1.5 outline-none cursor-pointer"
              aria-label={t("common.language")}
            >
              {LANGUAGES.map((l) => (
                <option key={l.code} value={l.code} className="bg-midnight">
                  {l.native}
                </option>
              ))}
            </select>
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold mt-3">{t("login.cardTitle")}</h1>
          <p className="text-white/55 text-sm mt-2">
            {t("login.subtitle")}
          </p>

          {mode === "demo" && (
            <div className="mt-5 flex items-start gap-2.5 rounded-2xl bg-mint/10 border border-mint/25 px-4 py-3">
              <Info size={15} className="text-mint mt-0.5 shrink-0" />
              <p className="text-[11px] text-white/70 leading-relaxed">
                <span className="font-bold text-mint">{t("common.demoMode")}.</span>{" "}
                {t("common.syntheticData")} — <span className="font-semibold text-white">{DEMO_CREDS.id}</span>{" "}
                / <span className="font-semibold text-white">{DEMO_CREDS.password}</span>
              </p>
            </div>
          )}

          {demoFilled && (
            <motion.div
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              className="mt-3 flex items-start gap-2.5 rounded-2xl bg-magenta/10 border border-magenta/30 px-4 py-3"
            >
              <Zap size={15} className="text-magenta mt-0.5 shrink-0" />
              <p className="text-[11px] text-white/80 leading-relaxed font-semibold">
                {t("login.demoFilled")}
              </p>
            </motion.div>
          )}

          <form onSubmit={submit} className="mt-6 space-y-4" noValidate>
            {/* Worker ID */}
            <div>
              <label className="block text-xs font-bold text-white/70 mb-1.5">
                {t("login.workerId")}
              </label>
              <input
                type="text"
                value={workerId}
                onChange={(e) => {
                  setWorkerId(e.target.value);
                  setDemoFilled(false);
                }}
                onFocus={() => setFocusField("workerId")}
                onBlur={() => setFocusField(null)}
                placeholder="e.g. ASHA001"
                autoComplete="username"
                className={`w-full rounded-xl bg-white/[0.07] border px-4 py-3 text-sm outline-none transition focus:border-mint/60 focus:bg-white/[0.1] ${
                  touched.workerId && !workerId.trim()
                    ? "border-coral/60"
                    : "border-white/10"
                }`}
              />
              {touched.workerId && !workerId.trim() && (
                <p className="text-[11px] text-coral mt-1.5">{t("login.errEmpty")}</p>
              )}
            </div>

            {/* Password */}
            <div>
              <label className="block text-xs font-bold text-white/70 mb-1.5">
                {t("login.password")}
              </label>
              <div className="relative">
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    setDemoFilled(false);
                  }}
                  onFocus={() => setFocusField("password")}
                  onBlur={() => setFocusField(null)}
                  placeholder="••••••••"
                  autoComplete="current-password"
                  className={`w-full rounded-xl bg-white/[0.07] border px-4 py-3 pr-12 text-sm outline-none transition focus:border-mint/60 focus:bg-white/[0.1] ${
                    touched.password && !password ? "border-coral/60" : "border-white/10"
                  }`}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-white/50 hover:text-mint transition"
                  aria-label={showPassword ? t("login.hidePassword") : t("login.showPassword")}
                >
                  {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
                </button>
              </div>
              {touched.password && !password && (
                <p className="text-[11px] text-coral mt-1.5">{t("login.errEmpty")}</p>
              )}
            </div>

            {/* Language */}
            <div>
              <label className="block text-xs font-bold text-white/70 mb-1.5">
                {t("common.language")}
              </label>
              <div className="relative">
                <select
                  value={language}
                  onChange={(e) => {
                    setLanguage(e.target.value);
                    setLang(e.target.value);
                  }}
                  className="w-full appearance-none rounded-xl bg-white/[0.07] border border-white/10 px-4 py-3 text-sm outline-none focus:border-mint/60 transition cursor-pointer"
                >
                  {LANGUAGES.map((l) => (
                    <option key={l.code} value={l.code} className="bg-midnight">
                      {l.native} — {l.label}
                    </option>
                  ))}
                </select>
                <ChevronDown size={15} className="absolute right-3.5 top-1/2 -translate-y-1/2 text-white/40 pointer-events-none" />
              </div>
            </div>

            {/* Remember / forgot */}
            <div className="flex items-center justify-between text-xs">
              <label className="flex items-center gap-2 cursor-pointer select-none text-white/65">
                <input
                  type="checkbox"
                  checked={remember}
                  onChange={(e) => setRemember(e.target.checked)}
                  className="accent-[#f078ad] w-4 h-4"
                />
                {t("login.rememberMe")}
              </label>
              <button
                type="button"
                onClick={() =>
                  setError(
                    t(
                      "login.forgotMsg",
                      "Password recovery is handled by your PHC coordinator in this prototype."
                    )
                  )
                }
                className="text-mint/90 hover:text-mint font-semibold"
              >
                {t("login.forgot")}
              </button>
            </div>

            {error && (
              <motion.p
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                className="text-[12px] text-coral bg-coral/10 border border-coral/25 rounded-xl px-4 py-2.5"
              >
                {error}
              </motion.p>
            )}

            {/* Primary sign-in */}
            <button
              type="submit"
              disabled={busy || success}
              className="btn-mint w-full py-3.5 text-sm flex items-center justify-center gap-2 disabled:opacity-70 disabled:cursor-not-allowed"
            >
              {busy ? (
                <>
                  <Loader2 size={16} className="animate-spin" /> {t("login.signingIn")}
                </>
              ) : success ? (
                <>
                  <Heart size={16} /> {t("login.success", "Welcome!").replace("{name}", "")}
                </>
              ) : (
                <>
                  <LogIn size={16} /> {t("login.signIn")}
                </>
              )}
            </button>

            {/* Prominent demo login */}
            <button
              type="button"
              onClick={tryDemo}
              disabled={busy || success}
              className="w-full py-3.5 text-sm flex items-center justify-center gap-2 rounded-xl font-bold border-2 border-magenta/50 text-magenta hover:bg-magenta/15 hover:border-magenta transition disabled:opacity-70 disabled:cursor-not-allowed"
            >
              <Sparkles size={16} /> {t("login.tryDemo")}
            </button>
          </form>

          <p className="text-[11px] text-white/40 mt-6 text-center leading-relaxed">
            {t(
              "login.privacy",
              "Protected by your PHC. Records stay private to authenticated ASHA workers."
            )}
          </p>
          <p className="text-center mt-3">
            <Link to="/" className="text-[11px] text-white/40 hover:text-mint">
              ← {t("nav.home")}
            </Link>
          </p>
        </motion.div>
      </div>
    </div>
  );
}

function TaraCanvas({ state, gaze, compact = false }) {
  return (
    <CanvasWrapper compact={compact}>
      <ambientLight intensity={0.6} />
      <directionalLight position={[2, 4, 5]} intensity={1.2} color="#eaf6ff" />
      <pointLight position={[-3, 2, 3]} intensity={1.2} color="#e84d9b" distance={8} />
      <pointLight position={[3, -1, 2]} intensity={0.7} color="#bba6ff" distance={7} />
      <group position={[0, 0.4, 0]} scale={compact ? 0.7 : 1}>
        <Tara state={state} gaze={gaze} scale={compact ? 0.75 : 1.05} />
      </group>
    </CanvasWrapper>
  );
}

function CanvasWrapper({ children, compact }) {
  return (
    <Canvas
      camera={{ position: [0, 1.1, 4.6], fov: compact ? 40 : 42 }}
      dpr={[1, 2]}
      gl={{ antialias: true, alpha: true }}
      style={{ background: "transparent" }}
    >
      {children}
    </Canvas>
  );
}
