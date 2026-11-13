import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Suspense, lazy } from "react";
import {
  Mic,
  Network,
  Activity,
  ShieldCheck,
  BellRing,
  Ear,
  Brain,
  Shield,
  ArrowRight,
  RotateCcw,
  Sparkles,
  HeartPulse,
  Baby,
  Stethoscope,
  QrCode,
  MessageSquareText,
  Syringe,
  UserCheck,
  Languages,
} from "lucide-react";
import { useI18n } from "../lib/i18n.jsx";

const HeroExperience = lazy(() => import("../components/three/HeroExperience.jsx"));

const fadeUp = {
  initial: { opacity: 0, y: 28 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, margin: "-80px" },
  transition: { duration: 0.7, ease: "easeOut" },
};

function Orb({ size = 12 }) {
  return (
    <span
      className="inline-block rounded-full"
      style={{
        width: size,
        height: size,
        background: "radial-gradient(circle at 35% 35%, #ffd3e6, #f078ad 55%, #8755d9)",
        boxShadow: "0 0 12px rgba(240,120,173,0.85), 0 0 34px rgba(187,166,255,0.4)",
      }}
    />
  );
}

function Nav() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  const { t, lang, setLang } = useI18n();
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    window.addEventListener("scroll", onScroll);
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const links = [
    [t("nav.home"), "#home"],
    [t("nav.features"), "#features"],
    [t("nav.howItWorks"), "#how-it-works"],
    [t("nav.about"), "#about"],
  ];

  return (
    <header
      className={`fixed top-0 inset-x-0 z-50 transition-all duration-300 bg-[#100C18]/35 backdrop-blur-md border-b border-white/5 ${
        scrolled ? "bg-[#100C18]/60 shadow-glass" : ""
      }`}
    >
      <nav className="max-w-7xl mx-auto flex items-center justify-between px-5 py-3.5">
        <a href="#home" className="flex items-center gap-2.5">
          <Orb size={13} />
          <div className="leading-tight">
            <div className="font-extrabold tracking-wide text-[15px]">{t("app.name")}</div>
            <div className="text-[10px] text-pink/80 tracking-[0.18em] uppercase">{t("app.tagline")}</div>
          </div>
        </a>
        <div className="hidden md:flex items-center gap-7 text-sm text-white/80">
          {links.map(([label, href]) => (
            <a key={href} href={href} className="whitespace-nowrap hover:text-pink transition-colors">
              {label}
            </a>
          ))}
          <LanguagePicker lang={lang} setLang={setLang} tone="dark" />
          <Link to="/login" className="btn-mint px-5 py-2 text-sm">
            {t("nav.login")}
          </Link>
        </div>
        <button
          className="md:hidden text-white/90"
          onClick={() => setOpen(!open)}
          aria-label={t("ld.toggleMenu", "Toggle menu")}
        >
          <div className="space-y-1.5">
            <span className={`block w-6 h-0.5 bg-white transition ${open ? "rotate-45 translate-y-2" : ""}`} />
            <span className={`block w-6 h-0.5 bg-white transition ${open ? "opacity-0" : ""}`} />
            <span className={`block w-6 h-0.5 bg-white transition ${open ? "-rotate-45 -translate-y-2" : ""}`} />
          </div>
        </button>
      </nav>
      {open && (
        <div className="md:hidden glass-strong px-6 py-5 space-y-4 text-sm">
          {links.map(([label, href]) => (
            <a key={href} href={href} onClick={() => setOpen(false)} className="block whitespace-nowrap text-white/85">
              {label}
            </a>
          ))}
          <div className="flex items-center gap-3">
            <LanguagePicker lang={lang} setLang={setLang} tone="dark" />
            <Link to="/login" className="btn-mint inline-block px-5 py-2">
              {t("nav.login")}
            </Link>
          </div>
        </div>
      )}
    </header>
  );
}

/** Compact language selector used on the landing page. */
function LanguagePicker({ lang, setLang, tone = "dark" }) {
  const { t } = useI18n();
  const options = [
    { code: "en", label: "English" },
    { code: "kn", label: "ಕನ್ನಡ" },
    { code: "hi", label: "हिन्दी" },
    { code: "te", label: "తెలుగు" },
    { code: "ta", label: "தமிழ்" },
  ];
  return (
    <label
      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[11px] font-bold tracking-wide ${
        tone === "dark"
          ? "glass text-white/80 cursor-pointer hover:text-white"
          : "bg-teal-deep/5 text-teal-deep/70 cursor-pointer hover:bg-teal-deep/10"
      }`}
      aria-label={t("ld.language", "Language")}
    >
      <Languages size={13} className="text-pink" />
      <select
        value={lang}
        onChange={(e) => setLang(e.target.value)}
        className="bg-transparent outline-none cursor-pointer [&>option]:text-teal-deep"
      >
        {options.map((o) => (
          <option key={o.code} value={o.code}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function Hero() {
  const [replayKey, setReplayKey] = useState(0);
  const [ready, setReady] = useState(false);
  const { t } = useI18n();

  /* floating HUD chips — 2D counterparts of the 3D holographic panels.
     Positioned to never collide with the headline (left), Tara (right of
     the worker) or the VOICE VISITS / PULSE THREAD panels. */
  const chips = [
    {
      icon: Syringe,
      tint: "#f078ad",
      title: t("ld.chip.vaccination", "Upcoming vaccination"),
      sub: t("ld.chip.vaccinationSub", "Ananya · 18 Nov"),
      className: "hidden xl:flex left-[43%] top-[15%]",
      delay: 0.1,
    },
    {
      icon: UserCheck,
      tint: "#bba6ff",
      title: t("ld.chip.followup", "Follow-up recorded"),
      sub: t("ld.chip.followupSub", "Lakshmi · ANC 28w"),
      className: "hidden xl:flex right-[21%] top-[12%]",
      delay: 0.25,
    },
    {
      icon: Activity,
      tint: "#ff806f",
      title: t("ld.chip.drift", "Pulse Drift"),
      sub: t("ld.chip.driftSub", "2 follow-ups due"),
      className: "hidden lg:flex right-[3%] bottom-[23%]",
      delay: 0.4,
    },
  ];

  return (
    <section id="home" className="relative min-h-screen overflow-hidden">
      {/* full-bleed immersive 3D world */}
      <div className="absolute inset-0">
        <Suspense
          fallback={
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="flex flex-col items-center gap-4">
                <motion.div
                  animate={{ scale: [1, 1.25, 1], opacity: [0.7, 1, 0.7] }}
                  transition={{ repeat: Infinity, duration: 1.8 }}
                >
                  <Orb size={46} />
                </motion.div>
                <p className="text-xs text-white/50 tracking-[0.2em] uppercase">
                  {t("ld.waking", "Waking up the hologram…")}
                </p>
              </div>
            </div>
          }
        >
          <HeroExperience key={replayKey} replayKey={replayKey} />
        </Suspense>
      </div>

      {/* subtle left legibility scrim — keeps the headline readable while
          letting the VOICE VISITS holographic panel glow through */}
      <div
        className="absolute inset-y-0 left-0 w-[58%] pointer-events-none"
        style={{
          background:
            "linear-gradient(90deg, rgba(16,12,24,0.72) 0%, rgba(16,12,24,0.38) 48%, rgba(16,12,24,0) 100%)",
        }}
      />
      {/* soft fade into the sections below */}
      <div
        className="absolute inset-x-0 bottom-0 h-28 pointer-events-none"
        style={{
          background:
            "linear-gradient(180deg, rgba(16,12,24,0) 0%, rgba(16,12,24,0.85) 100%)",
        }}
      />

      {/* floating HUD chips (2D holographic counterparts) */}
      {chips.map((chip) => (
        <motion.div
          key={chip.title}
          initial={{ opacity: 0, y: 14 }}
          animate={ready ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.7, ease: "easeOut", delay: chip.delay }}
          className={`absolute z-10 pointer-events-none ${chip.className}`}
        >
          <div className="glass-strong rounded-2xl px-3.5 py-2.5 flex items-center gap-2.5 shadow-glass">
            <div
              className="w-8 h-8 rounded-xl flex items-center justify-center shrink-0"
              style={{ background: `${chip.tint}1f`, boxShadow: `0 0 18px ${chip.tint}30` }}
            >
              <chip.icon size={15} style={{ color: chip.tint }} />
            </div>
            <div className="leading-tight">
              <p className="text-[11px] font-bold text-white/90">{chip.title}</p>
              <p className="text-[10px] text-white/45">{chip.sub}</p>
            </div>
          </div>
        </motion.div>
      ))}

      {/* hero text — LEFT FOREGROUND, separate from the 3D characters */}
      <div className="relative z-10 pointer-events-none min-h-screen flex items-center">
        <div className="w-full max-w-7xl mx-auto px-6 sm:px-10 lg:px-16">
          <div className="max-w-xl">
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={ready ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.7, ease: "easeOut" }}
              className="inline-flex items-center gap-2 glass rounded-full px-4 py-1.5 text-[11px] tracking-[0.16em] uppercase text-pink mb-5"
            >
              <Sparkles size={13} /> {t("ld.companion", "Your AI-Powered Healthcare Companion")}
            </motion.div>

            <motion.h1
              initial={{ opacity: 0, y: 26 }}
              animate={ready ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.8, ease: "easeOut", delay: 0.12 }}
              className="text-4xl sm:text-5xl lg:text-[3.4rem] font-extrabold leading-[1.08]"
            >
              {t("ld.heroLine1", "Every")}{" "}
              <span className="text-gradient-pink">{t("ld.heroWord1", "Voice")}</span>{" "}
              {t("ld.heroLine1b", "Matters.")}
              <br />
              <span className="text-gradient-lav">{t("ld.heroLine2", "Every Life Counts.")}</span>
            </motion.h1>

            <motion.p
              initial={{ opacity: 0, y: 20 }}
              animate={ready ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.8, ease: "easeOut", delay: 0.26 }}
              className="mt-4 text-[#c7b8c9] text-sm sm:text-base max-w-md leading-relaxed"
            >
              {t(
                "ld.heroSub",
                "Meet ASHA Swar Nirantar — your intelligent voice companion for easier healthcare fieldwork."
              )}
            </motion.p>

            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={ready ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.8, ease: "easeOut", delay: 0.4 }}
              className="mt-7 flex flex-wrap gap-4 pointer-events-auto"
            >
              <Link to="/login" className="btn-mint px-7 py-3.5 text-sm inline-flex items-center gap-2">
                {t("nav.getStarted")} <ArrowRight size={16} />
              </Link>
              <a href="#features" className="btn-ghost px-7 py-3.5 text-sm inline-flex items-center gap-2 glass">
                {t("nav.exploreFeatures")}
              </a>
            </motion.div>

            <motion.div
              initial={{ opacity: 0 }}
              animate={ready ? { opacity: 1 } : {}}
              transition={{ duration: 0.8, ease: "easeOut", delay: 0.55 }}
              className="mt-8 hidden sm:flex items-center gap-5 text-[11px] tracking-[0.14em] uppercase text-white/45"
            >
              <span className="inline-flex items-center gap-1.5">
                <Ear size={13} className="text-pink" /> {t("app.listen")}
              </span>
              <span className="inline-flex items-center gap-1.5">
                <Brain size={13} className="text-lavender" /> {t("app.remember")}
              </span>
              <span className="inline-flex items-center gap-1.5">
                <Shield size={13} className="text-coral" /> {t("app.protect")}
              </span>
            </motion.div>
          </div>
        </div>
      </div>

      {/* replay + disclaimer pinned to the bottom */}
      <div className="absolute bottom-4 inset-x-0 z-10 flex items-end justify-between px-5 sm:px-8 gap-3 pointer-events-none">
        <p className="hidden sm:block text-[10px] text-white/35 max-w-[210px] leading-snug">
          {t(
            "ld.qrDecorative",
            "The holographic QR is a decorative visual — it is not a scannable beneficiary code."
          )}
        </p>
        <button
          onClick={() => setReplayKey((k) => k + 1)}
          className="pointer-events-auto btn-ghost px-4 py-2 text-xs inline-flex items-center gap-2 glass"
        >
          <RotateCcw size={13} /> {t("ld.replay", "Replay introduction")}
        </button>
        <p className="hidden sm:block text-[10px] text-white/25 max-w-[210px] leading-snug text-right">
          {t("ld.syntheticOnly", "Synthetic demo data only.")}
        </p>
      </div>

      {/* marks hero timeline done for entrance animations */}
      <HeroReadiness onReady={setReady} />
    </section>
  );
}

function HeroReadiness({ onReady }) {
  useEffect(() => {
    const id = setTimeout(() => onReady(true), 1400);
    return () => clearTimeout(id);
  }, [onReady]);
  return null;
}

/* ============================== SECTIONS ============================== */

function FeatureCard({ icon: Icon, title, children, tint = "#f078ad" }) {
  return (
    <motion.div {...fadeUp} className="glass rounded-3xl p-7 hover:border-pink/40 transition-colors group">
      <div
        className="w-12 h-12 rounded-2xl flex items-center justify-center mb-5 group-hover:scale-110 transition-transform"
        style={{ background: `${tint}1f`, boxShadow: `0 0 24px ${tint}33` }}
      >
        <Icon size={22} style={{ color: tint }} />
      </div>
      <h3 className="font-bold text-lg mb-2.5">{title}</h3>
      <p className="text-sm text-[#c7b8c9]/80 leading-relaxed">{children}</p>
    </motion.div>
  );
}

function SectionBackdrop({ id, children, className = "" }) {
  return (
    <div
      id={id}
      className={`relative ${className}`}
      style={{
        background:
          "linear-gradient(180deg, rgba(33,19,41,0.0) 0%, rgba(33,19,41,0.9) 12%, rgba(33,19,41,0.9) 88%, rgba(33,19,41,0.0) 100%)",
      }}
    >
      {children}
    </div>
  );
}

function Features() {
  const { t } = useI18n();
  return (
    <SectionBackdrop id="features">
      <section className="relative max-w-7xl mx-auto px-5 py-24">
        <motion.div {...fadeUp} className="text-center mb-14">
          <p className="section-eyebrow mb-3">{t("ld.capabilities", "Capabilities")}</p>
          <h2 className="text-3xl sm:text-4xl font-extrabold">
            {t("ld.featuresTitle1", "Built around the")}{" "}
            <span className="text-gradient-pink">{t("ld.featuresWord", "voice")}</span>,{" "}
            {t("ld.featuresTitle2", "not the keyboard.")}
          </h2>
          <p className="text-[#c7b8c9]/80 mt-4 max-w-2xl mx-auto text-sm sm:text-base">
            {t(
              "ld.featuresSub",
              "Lengthy registers become simple conversations. The system connects what it hears into living health histories."
            )}
          </p>
        </motion.div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          <FeatureCard icon={Mic} title={t("ld.f1.title", "Voice-first recording")}>
            {t(
              "ld.f1.body",
              "Record pregnancy visits, newborn details, immunisations and follow-ups by speaking naturally — no lengthy typing in the field."
            )}
          </FeatureCard>
          <FeatureCard icon={Network} title={t("card.pulseThread.title", "Pulse Thread")} tint="#bba6ff">
            {t(
              "ld.f2.body",
              "Every record connects through a unique beneficiary ID — a longitudinal timeline of ANC checkups, weights, vaccines and newborn visits."
            )}
          </FeatureCard>
          <FeatureCard icon={Activity} title={t("card.pulseDrift.title", "Pulse Drift")} tint="#bba6ff">
            {t(
              "ld.f3.body",
              "Deterministic rules quietly surface overdue checkups, missed vaccination schedules and missing expected records for timely follow-up."
            )}
          </FeatureCard>
          <FeatureCard icon={ShieldCheck} title={t("ld.f4.title", "Safe danger-sign detection")} tint="#ff806f">
            {t(
              "ld.f4.body",
              "Detects approved warning phrases with correct negation handling, shows the exact triggering phrase, and says: refer to PHC as per approved guidelines."
            )}
          </FeatureCard>
          <FeatureCard icon={BellRing} title={t("ld.f5.title", "Smart reminders")}>
            {t(
              "ld.f5.body",
              "Schedule pregnancy checkups, vaccination and newborn follow-up reminders — with consent-based, non-sensitive SMS notifications."
            )}
          </FeatureCard>
          <FeatureCard icon={QrCode} title={t("ld.f6.title", "QR beneficiary profiles")} tint="#8755d9">
            {t(
              "ld.f6.body",
              "Each beneficiary carries an anonymous QR identity. Scan to open their connected history — never health data inside the code itself."
            )}
          </FeatureCard>
        </div>
      </section>
    </SectionBackdrop>
  );
}

function Steps() {
  const { t } = useI18n();
  const steps = [
    {
      icon: Ear,
      title: t("app.listen"),
      text: t(
        "ld.s1",
        "Understand the ASHA worker's voice — in her language, with natural code-mixing."
      ),
    },
    {
      icon: Brain,
      title: t("app.remember"),
      text: t(
        "ld.s2",
        "Maintain connected health histories so no detail is ever lost between visits."
      ),
    },
    {
      icon: Shield,
      title: t("app.protect"),
      text: t(
        "ld.s3",
        "Identify predefined danger signs and support timely, guideline-backed follow-ups."
      ),
    },
  ];
  return (
    <section className="relative max-w-7xl mx-auto px-5 py-16">
      <div className="glass rounded-[2rem] p-8 sm:p-12">
        <div className="grid md:grid-cols-3 gap-10 relative">
          <div className="hidden md:block absolute top-9 left-[16%] right-[16%] divider-fade" />
          {steps.map((s, i) => (
            <motion.div
              key={s.title}
              {...fadeUp}
              transition={{ ...fadeUp.transition, delay: i * 0.15 }}
              className="text-center relative"
            >
              <div className="w-[72px] h-[72px] mx-auto rounded-full glass flex items-center justify-center mb-5 relative z-10 bg-bg-base/60">
                <s.icon size={28} className="text-pink" />
              </div>
              <h3 className="font-extrabold tracking-[0.2em] text-sm mb-3">{s.title}</h3>
              <p className="text-sm text-[#c7b8c9]/80 max-w-xs mx-auto leading-relaxed">{s.text}</p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}

function HowItWorks() {
  const { t } = useI18n();
  const flow = [
    {
      n: "01",
      icon: Mic,
      title: t("ld.w1", "Speak"),
      text: t(
        "ld.w1b",
        "“Visited Lakshmi today. She is 28 weeks pregnant. Blood pressure is 120 over 80. Weight is 53 kilograms.”"
      ),
    },
    {
      n: "02",
      icon: Ear,
      title: t("ld.w2", "Transcribe"),
      text: t("ld.w2b", "Gnani Prisma v3.0 streams the speech into text, live and language-aware."),
    },
    {
      n: "03",
      icon: Brain,
      title: t("ld.w3", "Extract"),
      text: t("ld.w3b", "The LLM structures the fields — beneficiary, weeks, BP, weight, visit date."),
    },
    {
      n: "04",
      icon: ShieldCheck,
      title: t("ld.w4", "Validate"),
      text: t(
        "ld.w4b",
        "A deterministic rules engine checks danger signs and follow-up status. It never diagnoses."
      ),
    },
    {
      n: "05",
      icon: MessageSquareText,
      title: t("ld.w5", "Read back"),
      text: t(
        "ld.w5b",
        "Gnani Timbre v3.0 speaks the record aloud. The worker corrects by voice — only the stated field changes."
      ),
    },
    {
      n: "06",
      icon: HeartPulse,
      title: t("ld.w6", "Save"),
      text: t(
        "ld.w6b",
        "Only after explicit confirmation. The visit joins the Pulse Thread and reminders can be scheduled."
      ),
    },
  ];
  return (
    <SectionBackdrop id="how-it-works">
      <section className="relative max-w-7xl mx-auto px-5 py-24">
        <motion.div {...fadeUp} className="text-center mb-14">
          <p className="section-eyebrow mb-3">{t("ld.howItWorks", "How it works")}</p>
          <h2 className="text-3xl sm:text-4xl font-extrabold">
            {t("ld.sixSteps", "Six steps.")}{" "}
            <span className="text-gradient-pink">{t("ld.oneConversation", "One conversation.")}</span>
          </h2>
        </motion.div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {flow.map((f, i) => (
            <motion.div
              key={f.n}
              {...fadeUp}
              transition={{ ...fadeUp.transition, delay: (i % 3) * 0.1 }}
              className="glass rounded-3xl p-7 relative overflow-hidden"
            >
              <span className="absolute -top-3 -right-1 text-[5rem] font-black text-white/[0.045] select-none">
                {f.n}
              </span>
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-xl bg-pink/10 flex items-center justify-center">
                  <f.icon size={19} className="text-pink" />
                </div>
                <h3 className="font-bold">{f.title}</h3>
              </div>
              <p className="text-sm text-[#c7b8c9]/80 leading-relaxed">{f.text}</p>
            </motion.div>
          ))}
        </div>
        <motion.div {...fadeUp} className="mt-10 glass rounded-3xl p-8 text-center">
          <p className="text-white/85 text-lg font-semibold max-w-3xl mx-auto leading-relaxed">
            {t("ld.pitch1", "“Other voice registers record")}{" "}
            <span className="text-white/50">{t("ld.pitch2", "what was said")}</span>.{" "}
            {t("ld.pitch3", "ASHA Swar Nirantar notices")}{" "}
            <span className="text-gradient-pink font-extrabold">{t("ld.pitch4", "what's changing")}</span>{" "}
            {t("ld.pitch5", "— and it does so safely.”")}
          </p>
        </motion.div>
      </section>
    </SectionBackdrop>
  );
}

function Benefits() {
  const { t } = useI18n();
  const items = [
    {
      icon: Stethoscope,
      title: t("ld.b1.title", "For ANC visits"),
      text: t(
        "ld.b1.body",
        "Weeks of pregnancy, BP, weight and haemoglobin captured in seconds — read back and confirmed before saving."
      ),
    },
    {
      icon: Baby,
      title: t("ld.b2.title", "For newborns"),
      text: t(
        "ld.b2.body",
        "Birth details, feeding, jaundice checks and weight tracking joined to the mother's thread."
      ),
    },
    {
      icon: ShieldCheck,
      title: t("ld.b3.title", "For immunisation"),
      text: t(
        "ld.b3.body",
        "Every dose recorded with the next due date — missed schedules surface automatically."
      ),
    },
    {
      icon: BellRing,
      title: t("ld.b4.title", "For follow-ups"),
      text: t(
        "ld.b4.body",
        "Pulse Drift shows overdue checkups and suggested actions; reminders go out with consent."
      ),
    },
  ];
  return (
    <SectionBackdrop id="about">
      <section className="relative max-w-7xl mx-auto px-5 py-24">
        <div className="grid lg:grid-cols-2 gap-12 items-center">
          <motion.div {...fadeUp}>
            <p className="section-eyebrow mb-3">{t("ld.benefitsEyebrow", "Benefits for ASHA workers")}</p>
            <h2 className="text-3xl sm:text-4xl font-extrabold leading-tight">
              {t("ld.lessPaper", "Less paperwork.")}
              <br />
              <span className="text-gradient-pink">{t("ld.morePresence", "More presence.")}</span>
            </h2>
            <p className="text-[#c7b8c9]/85 mt-5 text-sm sm:text-base leading-relaxed max-w-lg">
              {t(
                "ld.benefitsBody",
                "ASHA workers are the heartbeat of village healthcare. Their time belongs with people — not registers. ASHA Swar Nirantar turns the field register into a conversation, keeps every history connected, and watches quietly over every follow-up."
              )}
            </p>
            <div className="mt-8 grid sm:grid-cols-2 gap-4">
              {items.map((it) => (
                <div key={it.title} className="glass rounded-2xl p-5">
                  <div className="flex items-center gap-2.5 mb-2">
                    <it.icon size={17} className="text-pink" />
                    <h4 className="font-bold text-sm">{it.title}</h4>
                  </div>
                  <p className="text-xs text-[#c7b8c9]/75 leading-relaxed">{it.text}</p>
                </div>
              ))}
            </div>
          </motion.div>

          <motion.div {...fadeUp} className="relative">
            <div className="glass rounded-[2rem] p-8 sm:p-10 relative overflow-hidden">
              <div
                className="absolute -top-24 -right-24 w-72 h-72 rounded-full pointer-events-none"
                style={{ background: "radial-gradient(circle, rgba(240,120,173,0.2), transparent 70%)" }}
              />
              {/* Tara & worker tag cards */}
              <div className="relative space-y-5">
                <div className="glass-strong rounded-2xl p-5 flex items-start gap-4">
                  <div className="w-11 h-11 rounded-full bg-pink/15 flex items-center justify-center shrink-0">
                    <Sparkles size={19} className="text-pink" />
                  </div>
                  <div>
                    <p className="text-sm font-bold mb-1">{t("ld.taraTitle", "Tara · AI companion")}</p>
                    <p className="text-xs text-[#c7b8c9]/80 leading-relaxed">
                      {t(
                        "ld.taraBody",
                        "“I've saved Lakshmi's visit — 28 weeks, BP 120/80, weight 54 kg. Her next ANC checkup is due in 12 days. Shall I schedule a reminder?”"
                      )}
                    </p>
                  </div>
                </div>
                <div className="glass-strong rounded-2xl p-5 flex items-start gap-4">
                  <div className="w-11 h-11 rounded-full bg-lavender/15 flex items-center justify-center shrink-0">
                    <Activity size={19} className="text-lavender" />
                  </div>
                  <div>
                    <p className="text-sm font-bold mb-1">{t("card.pulseThread.title", "Pulse Thread")}</p>
                    <p className="text-xs text-[#c7b8c9]/80 leading-relaxed">
                      {t(
                        "ld.threadBody",
                        "Mother & child histories, connected by one anonymous QR identity — visible in a single glance."
                      )}
                    </p>
                  </div>
                </div>
                <div
                  className="glass-strong rounded-2xl p-5 flex items-start gap-4"
                  style={{ borderColor: "rgba(255,128,111,0.35)" }}
                >
                  <div className="w-11 h-11 rounded-full bg-coral/15 flex items-center justify-center shrink-0">
                    <ShieldCheck size={19} className="text-coral" />
                  </div>
                  <div>
                    <p className="text-sm font-bold mb-1">{t("ld.safetyTitle", "Safety first")}</p>
                    <p className="text-xs text-[#c7b8c9]/80 leading-relaxed">
                      {t(
                        "ld.safetyBody",
                        "Rule-based danger-sign detection using the approved list. Tara never diagnoses — she flags verified phrases: “Refer to PHC as per approved guidelines.”"
                      )}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </motion.div>
        </div>
      </section>
    </SectionBackdrop>
  );
}

function FinalCTA() {
  const { t } = useI18n();
  return (
    <section className="relative max-w-7xl mx-auto px-5 pb-24">
      <motion.div
        {...fadeUp}
        className="relative rounded-[2.5rem] overflow-hidden p-12 sm:p-20 text-center"
        style={{
          background:
            "linear-gradient(140deg, rgba(232,77,155,0.16), rgba(135,85,217,0.12)), linear-gradient(160deg, #28152d, #100c18)",
          border: "1px solid rgba(240,120,173,0.28)",
        }}
      >
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background: "radial-gradient(600px 300px at 50% 0%, rgba(232,77,155,0.14), transparent)",
          }}
        />
        <div className="relative">
          <Orb size={18} />
          <h2 className="text-3xl sm:text-5xl font-extrabold mt-6 leading-tight">
            {t("ld.readyLine1", "Ready to give every village")}
            <br />
            <span className="text-gradient-pink">{t("ld.readyLine2", "its voice pulse?")}</span>
          </h2>
          <p className="text-[#c7b8c9]/85 mt-5 max-w-xl mx-auto text-sm sm:text-base">
            {t("ld.readyBody", "Sign in and start your first voice visit. Tara is waiting to listen.")}
          </p>
          <Link
            to="/login"
            className="btn-mint inline-flex items-center gap-2 px-8 py-4 mt-8 text-sm"
          >
            {t("nav.getStarted")} <ArrowRight size={16} />
          </Link>
        </div>
      </motion.div>
    </section>
  );
}

function Footer() {
  const { t } = useI18n();
  return (
    <footer className="border-t border-white/5 py-10">
      <div className="max-w-7xl mx-auto px-5 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-white/40">
        <div className="flex items-center gap-2.5">
          <Orb size={10} />
          <span className="font-bold text-white/70">{t("app.name")}</span>
          <span>· {t("app.tagline")}</span>
        </div>
        <p className="text-center sm:text-right">
          {t("ld.footerLine", "Every Voice Matters. Every Life Counts. · Synthetic demo data only")}
        </p>
      </div>
    </footer>
  );
}

export default function Landing() {
  return (
    <div className="min-h-screen bg-bg-base">
      <Nav />
      <Hero />
      <Features />
      <Steps />
      <HowItWorks />
      <Benefits />
      <FinalCTA />
      <Footer />
    </div>
  );
}
