import React, { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  LayoutDashboard,
  Users,
  Mic,
  QrCode,
  Waves,
  TrendingDown,
  ShieldAlert,
  BellRing,
  Settings as SettingsIcon,
  LogOut,
  ChevronLeft,
  ChevronRight,
  X,
  Radio,
  Home as HomeIcon,
  Droplets,
  HelpCircle,
  UserCog,
  Info,
  MessageSquare,
  ShieldQuestion,
  Menu,
  HeartHandshake,
  ClipboardList,
  Sparkles,
  Send,
  FlaskConical,
  MapPinned,
} from "lucide-react";
import { useAuth } from "../../lib/auth.jsx";
import { api, LANGUAGES } from "../../lib/api.js";
import { useI18n } from "../../lib/i18n.jsx";

/* ------------------------------ navigation ------------------------------ */

const NAV_KEYS = {
  "/app": "nav.dashboard",
  "/app/voice-visit": "nav.newVoiceVisit",
  "/app/households": "nav.households",
  "/app/beneficiaries": "nav.beneficiaries",
  "/app/qr-scanner": "nav.qrScanner",
  "/app/pulse-thread": "nav.pulseThread",
  "/app/pulse-drift": "nav.pulseDrift",
  "/app/geopulse": "nav.geopulse",
  "/app/reminders": "nav.smartReminders",
  "/app/notifications": "nav.notifications",
  "/app/settings": "nav.settings",
};

const NAV = [
  { to: "/app", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/app/voice-visit", label: "New Voice Visit", icon: Mic, core: true },
  { to: "/app/households", label: "Households", icon: HomeIcon, end: true },
  { to: "/app/beneficiaries", label: "Beneficiaries", icon: Users, end: true },
  { to: "/app/qr-scanner", label: "QR Scanner", icon: QrCode },
  { to: "/app/pulse-thread", label: "Pulse Thread", icon: Waves },
  { to: "/app/pulse-drift", label: "Pulse Drift", icon: TrendingDown },
  { to: "/app/geopulse", label: "GeoPulse Map", icon: MapPinned },
  // SMS uses existing TextBee integration. Sending is guarded by consent, compliance approval, config, and explicit confirmation.
  { to: "/app/reminders", label: "SMS Reminders", icon: BellRing },
  { to: "/app/notifications?tab=history", label: "SMS Delivery History", icon: MessageSquare },
  { to: "/app/settings", label: "Settings", icon: SettingsIcon },
];

function greetingKey(d = new Date()) {
  const h = d.getHours();
  if (h < 12) return "dash.goodMorning";
  if (h < 17) return "dash.goodAfternoon";
  return "dash.goodEvening";
}

/* ------------------------------ sidebar link ------------------------------ */

function SideLink({ item, label, collapsed, count, onNavigate }) {
  const Icon = item.icon;
  return (
    <NavLink
      to={item.to}
      end={item.end}
      title={collapsed ? label : undefined}
      onClick={onNavigate}
      className={({ isActive }) =>
        [
          "group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold transition-all duration-200",
          isActive
            ? "bg-[#7A1638] text-[#FFF7F0] border-l-4 border-[#E8A8B8]"
            : "text-[#FFF7F0]/80 hover:bg-[#881144] hover:text-[#FFF7F0] border-l-4 border-transparent",
          collapsed ? "justify-center px-2" : "",
        ].join(" ")
      }
    >
      <span className="relative shrink-0 text-[#E8A8B8]">
        <Icon size={19} strokeWidth={2.2} />
        {item.badge && count > 0 && (
          <span className="absolute -right-1.5 -top-1.5 flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-[#B4233F] px-1 text-[0.62rem] font-extrabold text-white">
            {count > 99 ? "99+" : count}
          </span>
        )}
      </span>
      {!collapsed && <span className="truncate">{label}</span>}
    </NavLink>
  );
}

function SidebarContent({ collapsed, onNavigate, onToggleCollapse, onLogout, t, showCollapse, isAdmin }) {
  const visibleNav = NAV.filter((item) => !item.admin || isAdmin);
  return (
    <>
      <div className="flex items-center gap-3 px-4 pb-5 pt-5">
        <div className="relative shrink-0">
          <div className="absolute inset-0 animate-pulseRing rounded-full bg-[#E8A8B8]/40" />
          <div className="relative flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-[#C64F78] to-[#7A1638] shadow-pinkGlow">
            <Radio size={18} className="text-[#FFF7F0]" />
          </div>
        </div>
        {!collapsed && (
          <div className="min-w-0">
            <p className="truncate text-[0.7rem] font-extrabold uppercase tracking-[0.18em] text-[#FFF7F0]">
              {t("app.name")}
            </p>
            <p className="mt-0.5 truncate text-[0.65rem] font-medium text-[#E8A8B8]/90">
              {t("app.tagline")}
            </p>
          </div>
        )}
      </div>

      <div className="mx-4 h-px bg-[#E8A8B8]/20" />

      <nav className="flex flex-1 flex-col gap-1.5 overflow-y-auto px-3 py-4">
        {visibleNav.map((item) => (
          <SideLink
            key={item.to}
            item={item}
            label={item.labelOverride || t(NAV_KEYS[item.to] || item.label)}
            collapsed={collapsed}
            count={0}
            onNavigate={onNavigate}
          />
        ))}
      </nav>

      <div className="space-y-1.5 border-t border-[#E8A8B8]/20 p-3">
        <button
          onClick={onLogout}
          className={[
            "flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold text-[#FFF7F0]/70 transition-colors hover:bg-[#881144] hover:text-[#FFF7F0]",
            collapsed ? "justify-center" : "",
          ].join(" ")}
        >
          <LogOut size={19} strokeWidth={2.2} />
          {!collapsed && <span>{t("nav.logout")}</span>}
        </button>
        {showCollapse && (
          <button
            onClick={onToggleCollapse}
            className="flex w-full items-center justify-center gap-2 rounded-xl px-3 py-2 text-xs font-semibold text-[#E8A8B8]/70 transition-colors hover:text-[#E8A8B8]"
          >
            {collapsed ? <ChevronRight size={16} /> : (
              <>
                <ChevronLeft size={16} />
                <span>{t("nav.collapse")}</span>
              </>
            )}
          </button>
        )}
      </div>
    </>
  );
}

/* --------------------------------- layout --------------------------------- */

export default function DashboardLayout() {
  const { user, logout, isAdmin } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const { t, lang, setLang } = useI18n();

  const [collapsed, setCollapsed] = useState(() => localStorage.getItem("asn_sidebar_collapsed") === "1");
  const [mobileOpen, setMobileOpen] = useState(false);
  const [sheet, setSheet] = useState(null); // null | "help" | "account" | "about"

  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  const toggleCollapse = () => {
    setCollapsed((c) => {
      localStorage.setItem("asn_sidebar_collapsed", c ? "0" : "1");
      return !c;
    });
  };

  const handleLogout = () => {
    logout();
    navigate("/");
  };

  const firstName = (user?.name || "Worker").trim().split(/\s+/)[0];
  const title = pageTitle(location.pathname);

  function pageTitle(pathname) {
    const clean = pathname.replace(/\/$/, "");
    if (clean === "/app" || clean === "/app/") return t("nav.dashboard");
    if (/\/beneficiaries\/[^/]+$/.test(clean)) return t("nav.pulseThread");
    if (/\/voice-visit/.test(clean)) return t("nav.newVoiceVisit");
    if (/\/households\/[^/]+$/.test(clean)) return t("nav.households");
    const found = NAV.filter((n) => clean === n.to || clean.startsWith(n.to + "/")).sort(
      (a, b) => b.to.length - a.to.length
    )[0];
    if (!found) return t("app.name");
    return found.labelOverride ? t(found.labelOverride) : t(NAV_KEYS[found.to] || found.label);
  }

  const [taraOpen, setTaraOpen] = useState(false);
  const [taraInput, setTaraInput] = useState("");
  const [taraBusy, setTaraBusy] = useState(false);
  const [taraMsgs, setTaraMsgs] = useState([]);

  useEffect(() => {
    setTaraMsgs((prev) => (prev.length === 0 ? [{ role: "assistant", text: t("tara.initial") }] : prev));
  }, [t]);

  const localTaraReply = (q) => {
    const lower = (q || "").toLowerCase();
    let reply = "I can help with ASHA field tasks: start a New Voice Visit, find households, review Pulse Thread history, check Pulse Drift follow-ups, and use GeoPulse for location-aware planning. I do not diagnose or prescribe.";
    if (lower.includes("remind") || lower.includes("follow") || lower.includes("due") || lower.includes("overdue"))
      reply = "Check Pulse Drift for overdue/upcoming follow-ups. Smart Reminders and Notifications show scheduled reminders and message history. Complete or reschedule follow-ups only after actual field action is recorded.";
    else if (lower.includes("alert") || lower.includes("danger") || lower.includes("referral"))
      reply = "Danger Alerts are deterministic, rule-based flags from recorded observations/phrases. They are not diagnoses. Review trigger evidence, follow approved referral protocol, and escalate/resolve with notes.";
    else if (lower.includes("voice") || lower.includes("record") || lower.includes("visit"))
      reply = "Use New Voice Visit to record by voice. Confirm beneficiary identity, review extracted fields, correct any field by voice/text, and explicitly confirm before saving. Each beneficiary gets their own record.";
    else if (lower.includes("map") || lower.includes("geopulse") || lower.includes("household location"))
      reply = "GeoPulse shows only actual stored household coordinates. Capture GPS with permission or enter verified manual coordinates before saving. Households without coordinates appear in the list fallback.";
    else if (lower.includes("qr") || lower.includes("scan"))
      reply = "Use QR Scanner to identify an existing beneficiary or household by QR/card ID. Verify the resolved record before taking action.";
    else if (lower.includes("history") || lower.includes("pulse thread"))
      reply = "Pulse Thread shows chronological recorded visits, measurements, maternal/newborn care, immunisation, and referrals for the selected beneficiary.";
    return reply;
  };

  const sendTara = async () => {
    const q = (taraInput || "").trim();
    if (!q || taraBusy) return;
    setTaraMsgs((m) => [...m, { role: "user", text: q }]);
    setTaraInput("");
    setTaraBusy(true);
    try {
      const res = await api.post("/voice/chat", { message: q, language: lang || "en" }, { redirectOnUnauthorized: true });
      const reply = (res?.reply || "").trim();
      if (!reply) throw new Error("Empty response");
      setTaraMsgs((m) => [...m, { role: "assistant", text: reply }]);
    } catch (e) {
      // Do not show a fake Gemini success; fall back to local guidance so assistance remains available.
      setTaraMsgs((m) => [...m, { role: "assistant", text: localTaraReply(q) }]);
    } finally {
      setTaraBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-ivory text-[#2B1F26]">
      {/* ------------------------------ desktop sidebar ------------------------------ */}
      <aside
        className={[
          "fixed inset-y-0 left-0 z-40 hidden flex-col border-r border-[#E8A8B8]/20 bg-[#321321] transition-[width] duration-300 lg:flex",
          collapsed ? "w-[76px]" : "w-64",
        ].join(" ")}
      >
        <SidebarContent
          collapsed={collapsed}
          onNavigate={undefined}
          onToggleCollapse={toggleCollapse}
          onLogout={handleLogout}
          t={t}
          showCollapse
          isAdmin={isAdmin}
        />
      </aside>

      {/* ------------------------------ mobile drawer sidebar ------------------------------ */}
      <AnimatePresence>
        {mobileOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-50 bg-[#321321]/60 backdrop-blur-sm lg:hidden"
              onClick={() => setMobileOpen(false)}
            />
            <motion.aside
              initial={{ x: -320 }}
              animate={{ x: 0 }}
              exit={{ x: -320 }}
              transition={{ type: "spring", damping: 28, stiffness: 320 }}
              className="fixed inset-y-0 left-0 z-50 flex w-72 max-w-[85vw] flex-col border-r border-[#E8A8B8]/20 bg-[#321321] lg:hidden"
            >
              <button
                onClick={() => setMobileOpen(false)}
                aria-label={t("common.close")}
                className="absolute right-3 top-3 rounded-lg p-2 text-[#E8A8B8]/80 hover:bg-[#881144] hover:text-[#FFF7F0]"
              >
                <X size={18} />
              </button>
              <SidebarContent
                collapsed={false}
                onNavigate={() => setMobileOpen(false)}
                onToggleCollapse={undefined}
                onLogout={handleLogout}
                t={t}
                showCollapse={false}
                isAdmin={isAdmin}
              />
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      {/* ------------------------------ main column ------------------------------ */}
      <div className={`transition-[padding] duration-300 ${collapsed ? "lg:pl-[76px]" : "lg:pl-64"}`}>
        <header className="sticky top-0 z-30 border-b border-[#EADCE1] bg-white/85 backdrop-blur-xl">
          <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-3 sm:px-6 lg:px-8">
            <button
              onClick={() => setMobileOpen(true)}
              aria-label={t("nav.openNavigation")}
              className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-[#EADCE1] bg-white text-[#7A1638] hover:bg-[#F4DCE4] lg:hidden"
            >
              <Menu size={18} />
            </button>
            <div className="hidden h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-[#C64F78] to-[#7A1638] lg:flex">
              <Radio size={16} className="text-[#FFF7F0]" />
            </div>
            <div className="min-w-0 flex-1">
              <h1 className="truncate text-lg font-extrabold text-[#2B1F26] sm:text-xl">{title}</h1>
            </div>
            <p className="hidden truncate text-sm font-semibold text-[#685B62] md:block">
              {t(greetingKey())}, {firstName}!
            </p>
            <select
              value={lang}
              onChange={(e) => setLang(e.target.value)}
              aria-label={t("common.language")}
              className="rounded-full border border-[#EADCE1] bg-white px-2.5 py-1.5 text-xs font-bold text-[#2B1F26] outline-none cursor-pointer hover:border-[#E8A8B8] focus:border-[#7A1638] transition"
            >
              {LANGUAGES.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.native}
                </option>
              ))}
            </select>
            <div className="hidden items-center gap-1 lg:flex">
              <button
                onClick={() => setSheet("help")}
                title={t("nav.help")}
                className="rounded-lg p-2 text-[#685B62] hover:bg-[#F4DCE4] hover:text-[#7A1638]"
              >
                <HelpCircle size={18} />
              </button>
              <button
                onClick={() => setSheet("account")}
                title={t("nav.account")}
                className="rounded-lg p-2 text-[#685B62] hover:bg-[#F4DCE4] hover:text-[#7A1638]"
              >
                <UserCog size={18} />
              </button>
              <button
                onClick={() => setSheet("about")}
                title={t("nav.about")}
                className="rounded-lg p-2 text-[#685B62] hover:bg-[#F4DCE4] hover:text-[#7A1638]"
              >
                <Info size={18} />
              </button>
            </div>
          </div>
        </header>

        <main className="mx-auto max-w-7xl px-4 pb-10 pt-5 sm:px-6 lg:px-8">
          <Outlet />
        </main>
      </div>

      {/* Global Tara assistant */}
      <button
        onClick={() => setTaraOpen((o) => !o)}
        className="fixed bottom-5 right-5 z-40 flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-[#C64F78] to-[#7A1638] text-white shadow-[0_10px_30px_rgba(122,22,56,0.35)] hover:brightness-110"
        aria-label={t("tara.open")}
        title={t("tara.open")}
      >
        <Sparkles size={22} />
      </button>
      <AnimatePresence>
        {taraOpen && (
          <motion.div
            initial={{ opacity: 0, y: 16, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 12, scale: 0.98 }}
            className="fixed bottom-24 right-5 z-40 w-[92vw] max-w-sm overflow-hidden rounded-3xl border border-[#EADCE1] bg-white shadow-card"
          >
            <div className="flex items-center justify-between border-b border-[#EADCE1] bg-[#FFF7F0] px-4 py-3">
              <div>
                <p className="text-sm font-extrabold text-[#2B1F26]">{t("tara.title")}</p>
                <p className="text-[0.65rem] font-semibold text-[#685B62]">{t("tara.subtitle")}</p>
              </div>
              <button onClick={() => setTaraOpen(false)} aria-label={t("common.close")} className="rounded-full p-1.5 text-[#685B62] hover:bg-[#F4DCE4]"><X size={15}/></button>
            </div>
            <div className="max-h-72 space-y-2 overflow-y-auto p-3">
              {taraMsgs.map((m, i) => (
                <div key={i} className={`rounded-2xl px-3 py-2 text-xs font-medium leading-relaxed ${m.role==='assistant' ? 'bg-[#F4DCE4]/60 text-[#2B1F26]' : 'bg-[#321321] text-white ml-6'}`}>{m.text}</div>
              ))}
            </div>
            <div className="flex items-center gap-2 border-t border-[#EADCE1] p-2.5">
              <input value={taraInput} onChange={(e)=>setTaraInput(e.target.value)} onKeyDown={(e)=>e.key==='Enter'&&sendTara()} placeholder={t("tara.placeholder")} className="flex-1 rounded-xl border border-[#EADCE1] bg-[#FFF7F0] px-3 py-2 text-xs font-medium text-[#2B1F26] outline-none focus:border-[#7A1638]" disabled={taraBusy} />
              <button onClick={sendTara} aria-label={t("common.submit")} className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#7A1638] text-white disabled:opacity-60" disabled={taraBusy || !taraInput.trim()}><Send size={14}/></button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ------------------------------ help / account / about sheet ------------------------------ */}
      <AnimatePresence>
        {sheet && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-end justify-center bg-[#321321]/50 backdrop-blur-sm sm:items-center sm:p-6"
            onClick={() => setSheet(null)}
          >
            <motion.div
              initial={{ y: 60, opacity: 0, scale: 0.98 }}
              animate={{ y: 0, opacity: 1, scale: 1 }}
              exit={{ y: 40, opacity: 0, scale: 0.98 }}
              transition={{ type: "spring", damping: 28, stiffness: 340 }}
              onClick={(e) => e.stopPropagation()}
              className="card-ivory max-h-[86vh] w-full max-w-md overflow-y-auto rounded-b-none p-6 sm:rounded-3xl"
            >
              <div className="mb-4 flex items-start justify-between gap-3">
                <h3 className="text-lg font-extrabold text-[#2B1F26]">
                  {sheet === "help"
                    ? t("help.title", "Help")
                    : sheet === "account"
                      ? t("nav.account", "Account")
                      : t("nav.about", "About")}
                </h3>
                <button
                  onClick={() => setSheet(null)}
                  aria-label={t("common.close")}
                  className="rounded-full bg-[#F4DCE4] p-2 text-[#7A1638] hover:bg-[#E8A8B8]/50"
                >
                  <X size={16} />
                </button>
              </div>

              {sheet === "help" && (
                <ul className="space-y-3">
                  {[
                    { icon: Mic, title: t("help.step1Title", "Record a visit"), text: t("help.step1", "Open Voice, tap the mic and speak naturally. Tara transcribes, extracts and reads it back before anything is saved.") },
                    { icon: QrCode, title: t("help.step2Title", "Scan a card"), text: t("help.step2", "Use QR Scanner to open a beneficiary or household by their card — the code holds an anonymous ID only.") },
                    { icon: TrendingDown, title: t("help.step3Title", "Check follow-ups"), text: t("help.step3", "Pulse Drift lists deterministic overdue items. Unchanged values are flagged for verification, never diagnosed.") },
                    { icon: ShieldAlert, title: t("help.step4Title", "Danger signs"), text: t("help.step4", "Approved warning phrases are flagged verbatim with a fixed referral message. Tara never diagnoses.") },
                  ].map((h) => (
                    <li key={h.title} className="flex items-start gap-3 rounded-2xl bg-[#FFF7F0] px-3.5 py-3 border border-[#EADCE1]">
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-[#F4DCE4]">
                        <h.icon size={15} className="text-[#7A1638]" strokeWidth={2.2} />
                      </div>
                      <div className="min-w-0">
                        <p className="text-xs font-extrabold text-[#2B1F26]">{h.title}</p>
                        <p className="mt-0.5 text-[0.7rem] font-medium leading-relaxed text-[#685B62]">{h.text}</p>
                      </div>
                    </li>
                  ))}
                </ul>
              )}

              {sheet === "account" && (
                <div className="space-y-3">
                  <div className="flex items-center gap-3 rounded-2xl bg-[#FFF7F0] border border-[#EADCE1] px-4 py-3.5">
                    <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-[#C64F78] to-[#7A1638] text-base font-extrabold text-white">
                      {(user?.name || "W")
                        .trim()
                        .split(/\s+/)
                        .slice(0, 2)
                        .map((w) => w[0]?.toUpperCase())
                        .join("")}
                    </div>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-extrabold text-[#2B1F26]">{user?.name || "—"}</p>
                      <p className="truncate text-xs font-medium text-[#685B62]">{t("settings.ashaWorker", "ASHA Worker")}</p>
                    </div>
                  </div>
                  <div className="space-y-1.5">
                    {[
                      [t("login.workerId"), user?.worker_id || "—"],
                      [t("common.village"), user?.phc || "—"],
                      [t("common.language"), LANGUAGES.find((l) => l.code === (user?.language || lang))?.native || "English"],
                    ].map(([k, v]) => (
                      <div key={k} className="flex items-center justify-between rounded-xl bg-[#FFF7F0] border border-[#EADCE1] px-4 py-2.5">
                        <span className="text-xs font-semibold text-[#685B62]">{k}</span>
                        <span className="text-xs font-extrabold text-[#2B1F26]">{v}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {sheet === "about" && (
                <div className="space-y-3 text-center">
                  <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-3xl bg-gradient-to-br from-[#C64F78] to-[#7A1638] text-white shadow-pinkGlow">
                    <Radio size={28} strokeWidth={2.2} />
                  </div>
                  <p className="text-lg font-extrabold text-[#2B1F26]">{t("app.name")}</p>
                  <p className="text-xs font-semibold uppercase tracking-wider text-[#7A1638]">{t("app.tagline")}</p>
                  <p className="text-sm font-medium leading-relaxed text-[#685B62]">
                    {t("settings.aboutDesc")}
                  </p>
                  <p className="text-[0.68rem] font-semibold text-[#685B62]">{t("settings.version", "Version 1.0.0")}</p>
                </div>
              )}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
