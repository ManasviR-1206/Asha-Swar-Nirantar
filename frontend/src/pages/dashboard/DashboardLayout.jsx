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
  MoreHorizontal,
  X,
  Radio,
  Home as HomeIcon,
  Droplets,
  HelpCircle,
  UserCog,
  Info,
} from "lucide-react";
import { useAuth } from "../../lib/auth.jsx";
import { api, LANGUAGES } from "../../lib/api.js";
import { useI18n } from "../../lib/i18n.jsx";

/* ------------------------------ navigation ------------------------------ */

const NAV_KEYS = {
  "/app": "nav.overview",
  "/app/beneficiaries": "nav.beneficiaries",
  "/app/households": "nav.households",
  "/app/voice-visit": "nav.newVoiceVisit",
  "/app/qr-scanner": "nav.qrScanner",
  "/app/household-health": "nav.householdHealth",
  "/app/pulse-thread": "nav.pulseThread",
  "/app/pulse-drift": "nav.pulseDrift",
  "/app/alerts": "nav.dangerAlerts",
  "/app/reminders": "nav.smartReminders",
  "/app/settings": "nav.settings",
};

const NAV = [
  { to: "/app", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/app/beneficiaries", label: "Beneficiaries", icon: Users, end: true },
  { to: "/app/households", label: "Households", icon: HomeIcon, end: true },
  { to: "/app/voice-visit", label: "New Voice Visit", icon: Mic, core: true },
  { to: "/app/qr-scanner", label: "QR Scanner", icon: QrCode },
  { to: "/app/household-health", label: "Household Health", icon: Droplets },
  { to: "/app/pulse-thread", label: "Pulse Thread", icon: Waves },
  { to: "/app/pulse-drift", label: "Pulse Drift", icon: TrendingDown },
  { to: "/app/alerts", label: "Danger Alerts", icon: ShieldAlert, badge: true },
  { to: "/app/reminders", label: "Smart Reminders", icon: BellRing },
  { to: "/app/settings", label: "Settings", icon: SettingsIcon },
];

const BOTTOM_NAV = [
  { to: "/app", label: "Home", icon: LayoutDashboard, end: true, key: "nav.home" },
  { to: "/app/voice-visit", label: "Voice", icon: Mic, core: true, key: "nav.voice" },
  { to: "/app/qr-scanner", label: "QR", icon: QrCode, key: "nav.qr" },
  { to: "/app/beneficiaries", label: "People", icon: Users, end: true, key: "nav.people" },
];

function greetingKey(d = new Date()) {
  const h = d.getHours();
  if (h < 12) return "dash.goodMorning";
  if (h < 17) return "dash.goodAfternoon";
  return "dash.goodEvening";
}

/* ------------------------------ sidebar link ------------------------------ */

function SideLink({ item, label, collapsed, count }) {
  const Icon = item.icon;
  return (
    <NavLink
      to={item.to}
      end={item.end}
      title={collapsed ? label : undefined}
      className={({ isActive }) =>
        [
          "group relative flex items-center gap-3 rounded-2xl px-3 py-2.5 text-sm font-semibold transition-all duration-200",
          item.core && !isActive ? "text-mint/90 hover:bg-white/5" : "",
          item.core && isActive
            ? "bg-mint text-teal-deep shadow-[0_6px_24px_rgba(240,120,173,0.4)]"
            : "",
          !item.core && isActive ? "bg-white/10 text-white" : "",
          !item.core && !isActive ? "text-white/55 hover:bg-white/5 hover:text-white/90" : "",
          collapsed ? "justify-center" : "",
        ].join(" ")
      }
    >
      <span className="relative shrink-0">
        <Icon size={19} strokeWidth={2.2} />
        {item.badge && count > 0 && (
          <span className="absolute -right-1.5 -top-1.5 flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-coral px-1 text-[0.62rem] font-extrabold text-white">
            {count > 99 ? "99+" : count}
          </span>
        )}
      </span>
      {!collapsed && <span className="truncate">{label}</span>}
    </NavLink>
  );
}

/* --------------------------------- layout --------------------------------- */

export default function DashboardLayout() {
  const { user, logout, mode } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const { t, lang, setLang } = useI18n();

  const [collapsed, setCollapsed] = useState(() => localStorage.getItem("asn_sidebar_collapsed") === "1");
  const [alertCount, setAlertCount] = useState(0);
  const [moreOpen, setMoreOpen] = useState(false);
  const [sheet, setSheet] = useState(null); // null | "help" | "account" | "about"

  useEffect(() => {
    let alive = true;
    const load = () =>
      api
        .get("/alerts")
        .then((d) => {
          if (alive) setAlertCount((d.alerts || []).filter((a) => a.status !== "acknowledged").length);
        })
        .catch(() => {});
    load();
    const t = setInterval(load, 60000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  // Close the "More" sheet whenever the route changes.
  useEffect(() => setMoreOpen(false), [location.pathname]);

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
  const moreItems = NAV.filter((n) => !BOTTOM_NAV.some((b) => b.to === n.to));

  function pageTitle(pathname) {
    const clean = pathname.replace(/\/$/, "");
    if (clean === "/app" || clean === "/app/") return t("nav.overview");
    if (/\/beneficiaries\/[^/]+$/.test(clean)) return t("nav.pulseThread");
    if (/\/voice-visit/.test(clean)) return t("nav.newVoiceVisit");
    if (/\/households\/[^/]+$/.test(clean)) return t("nav.households");
    // Longest route wins so "/app/pulse-drift" is not swallowed by "/app".
    const found = NAV.filter((n) => clean === n.to || clean.startsWith(n.to + "/")).sort(
      (a, b) => b.to.length - a.to.length
    )[0];
    if (!found) return t("nav.overview");
    return t(NAV_KEYS[found.to] || "nav.overview");
  }

  return (
    <div className="min-h-screen bg-ivory text-teal-deep">
      {/* ------------------------------ sidebar ------------------------------ */}
      <aside
        className={[
          "fixed inset-y-0 left-0 z-40 hidden flex-col bg-teal-deep text-white transition-[width] duration-300 lg:flex",
          collapsed ? "w-[76px]" : "w-64",
        ].join(" ")}
      >
        {/* logo block */}
        <div className="flex items-center gap-3 px-4 pb-6 pt-6">
          <div className="relative shrink-0">
            <div className="absolute inset-0 animate-pulseRing rounded-full bg-mint/50" />
            <div className="relative flex h-10 w-10 items-center justify-center rounded-full bg-mint shadow-[0_0_28px_rgba(240,120,173,0.8)]">
              <Radio size={18} className="text-teal-deep" />
            </div>
          </div>
          {!collapsed && (
            <div className="min-w-0">
              <p className="truncate text-[0.7rem] font-extrabold uppercase tracking-[0.18em] text-white">
                {t("app.name")}
              </p>
              <p className="mt-0.5 truncate text-[0.65rem] font-medium text-mint/80">
                {t("app.tagline")}
              </p>
            </div>
          )}
        </div>

        <div className="mx-4 divider-fade opacity-40" />

        {/* nav */}
        <nav className="flex flex-1 flex-col gap-1.5 overflow-y-auto px-3 py-4">
          {NAV.map((item) => (
            <SideLink
              key={item.to}
              item={item}
              label={t(NAV_KEYS[item.to] || item.label)}
              collapsed={collapsed}
              count={alertCount}
            />
          ))}
        </nav>

        {/* logout + collapse */}
        <div className="space-y-1.5 border-t border-white/10 p-3">
          <button
            onClick={handleLogout}
            className={[
              "flex w-full items-center gap-3 rounded-2xl px-3 py-2.5 text-sm font-semibold text-white/55 transition-colors hover:bg-coral/15 hover:text-coral",
              collapsed ? "justify-center" : "",
            ].join(" ")}
          >
            <LogOut size={19} strokeWidth={2.2} />
            {!collapsed && <span>{t("nav.logout")}</span>}
          </button>
          <button
            onClick={toggleCollapse}
            className="flex w-full items-center justify-center gap-2 rounded-2xl px-3 py-2 text-xs font-semibold text-white/40 transition-colors hover:text-white/80"
          >
            {collapsed ? <ChevronRight size={16} /> : (
              <>
                <ChevronLeft size={16} />
                <span>Collapse</span>
              </>
            )}
          </button>
        </div>
      </aside>

      {/* ------------------------------ main column ------------------------------ */}
      <div className={`transition-[padding] duration-300 ${collapsed ? "lg:pl-[76px]" : "lg:pl-64"}`}>
        {/* glass topbar */}
        <header className="sticky top-0 z-30 border-b border-teal-deep/10 bg-white/70 backdrop-blur-xl">
          <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-3 sm:px-6 lg:px-8">
            <div className="lg:hidden flex h-9 w-9 items-center justify-center rounded-full bg-teal-deep">
              <Radio size={16} className="text-mint" />
            </div>
            <div className="min-w-0 flex-1">
              <h1 className="truncate text-lg font-extrabold text-teal-deep sm:text-xl">{title}</h1>
            </div>
            <p className="hidden truncate text-sm font-semibold text-teal-deep/70 md:block">
              {t(greetingKey())}, {firstName}!
            </p>
            {/* functional UI language selector */}
            <select
              value={lang}
              onChange={(e) => setLang(e.target.value)}
              aria-label={t("common.language")}
              className="rounded-full border border-teal-deep/15 bg-white px-2.5 py-1.5 text-xs font-bold text-teal-deep outline-none cursor-pointer hover:border-teal-deep/30 transition"
            >
              {LANGUAGES.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.native}
                </option>
              ))}
            </select>
            <span
              className={`chip ${
                mode === "live" ? "bg-mint/15 text-pink" : "bg-lavender/20 text-midnight"
              }`}
            >
              {mode === "live" ? "Live" : t("common.demoMode")}
            </span>
            <button
              onClick={handleLogout}
              aria-label={t("nav.logout")}
              className="rounded-full p-2 text-teal-deep/60 transition-colors hover:bg-coral/10 hover:text-coral lg:hidden"
            >
              <LogOut size={18} />
            </button>
          </div>
        </header>

        {/* page content */}
        <main className="mx-auto max-w-7xl px-4 pb-28 pt-5 sm:px-6 lg:px-8 lg:pb-10">
          <Outlet />
        </main>
      </div>

      {/* ------------------------------ mobile bottom nav ------------------------------ */}
      <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-teal-deep/10 bg-white/90 backdrop-blur-xl lg:hidden">
        <div className="mx-auto flex max-w-lg items-stretch justify-between px-2 py-1.5">
          {BOTTOM_NAV.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  [
                    "flex min-w-0 flex-1 flex-col items-center gap-0.5 rounded-2xl px-1 py-1.5 text-[0.62rem] font-bold transition-colors",
                    isActive
                      ? item.core
                        ? "bg-mint text-teal-deep"
                        : "bg-mint/15 text-pink"
                      : item.core
                        ? "text-mint"
                        : "text-teal-deep/45",
                  ].join(" ")
                }
              >
                <Icon size={20} strokeWidth={2.2} />
                <span className="truncate">{t(item.key, item.label)}</span>
              </NavLink>
            );
          })}
          <button
            onClick={() => setMoreOpen(true)}
            className="flex min-w-0 flex-1 flex-col items-center gap-0.5 rounded-2xl px-1 py-1.5 text-[0.62rem] font-bold text-teal-deep/45 transition-colors"
          >
            <MoreHorizontal size={20} strokeWidth={2.2} />
            <span>{t("nav.more")}</span>
          </button>
        </div>
      </nav>

      {/* ------------------------------ "More" sheet ------------------------------ */}
      <AnimatePresence>
        {moreOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 bg-teal-deep/50 backdrop-blur-sm lg:hidden"
            onClick={() => setMoreOpen(false)}
          >
            <motion.div
              initial={{ y: "100%" }}
              animate={{ y: 0 }}
              exit={{ y: "100%" }}
              transition={{ type: "spring", damping: 30, stiffness: 320 }}
              onClick={(e) => e.stopPropagation()}
              className="absolute inset-x-0 bottom-0 rounded-t-3xl bg-ivory p-5 pb-8"
            >
              <div className="mx-auto mb-4 h-1.5 w-12 rounded-full bg-teal-deep/15" />
              <div className="mb-3 flex items-center justify-between">
                <p className="text-sm font-extrabold uppercase tracking-wider text-teal-deep/60">{t("nav.more")}</p>
                <button
                  onClick={() => setMoreOpen(false)}
                  aria-label={t("common.close")}
                  className="rounded-full bg-teal-deep/5 p-2 text-teal-deep/60"
                >
                  <X size={18} />
                </button>
              </div>
              <div className="grid grid-cols-2 gap-2.5">
                {moreItems.map((item) => {
                  const Icon = item.icon;
                  return (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      className={({ isActive }) =>
                        [
                          "flex items-center gap-2.5 rounded-2xl px-3.5 py-3 text-sm font-bold transition-colors",
                          isActive ? "bg-mint/15 text-pink" : "bg-white text-teal-deep/70 shadow-soft",
                        ].join(" ")
                      }
                    >
                      <span className="relative">
                        <Icon size={18} strokeWidth={2.2} />
                        {item.badge && alertCount > 0 && (
                          <span className="absolute -right-2 -top-2 flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-coral px-1 text-[0.6rem] font-extrabold text-white">
                            {alertCount}
                          </span>
                        )}
                      </span>
                      <span className="min-w-0 truncate">{t(NAV_KEYS[item.to] || item.label)}</span>
                    </NavLink>
                  );
                })}
                <button
                  onClick={() => {
                    setMoreOpen(false);
                    setSheet("help");
                  }}
                  className="flex items-center gap-2.5 rounded-2xl bg-white px-3.5 py-3 text-sm font-bold text-teal-deep/70 shadow-soft transition-colors hover:bg-mint-soft"
                >
                  <HelpCircle size={18} strokeWidth={2.2} className="text-pink" />
                  <span className="min-w-0 truncate">{t("nav.help")}</span>
                </button>
                <button
                  onClick={() => {
                    setMoreOpen(false);
                    setSheet("account");
                  }}
                  className="flex items-center gap-2.5 rounded-2xl bg-white px-3.5 py-3 text-sm font-bold text-teal-deep/70 shadow-soft transition-colors hover:bg-mint-soft"
                >
                  <UserCog size={18} strokeWidth={2.2} className="text-pink" />
                  <span className="min-w-0 truncate">{t("nav.account")}</span>
                </button>
                <button
                  onClick={() => {
                    setMoreOpen(false);
                    setSheet("about");
                  }}
                  className="flex items-center gap-2.5 rounded-2xl bg-white px-3.5 py-3 text-sm font-bold text-teal-deep/70 shadow-soft transition-colors hover:bg-mint-soft"
                >
                  <Info size={18} strokeWidth={2.2} className="text-pink" />
                  <span className="min-w-0 truncate">{t("nav.about")}</span>
                </button>
                <button
                  onClick={handleLogout}
                  className="col-span-2 mt-1 flex items-center justify-center gap-2 rounded-2xl bg-coral/10 px-3.5 py-3 text-sm font-bold text-coral"
                >
                  <LogOut size={18} strokeWidth={2.2} />
                  {t("nav.logout")}
                </button>
              </div>
            </motion.div>
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
            className="fixed inset-0 z-50 flex items-end justify-center bg-teal-deep/50 backdrop-blur-sm sm:items-center sm:p-6"
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
                <h3 className="text-lg font-extrabold text-teal-deep">
                  {sheet === "help"
                    ? t("help.title", "Help")
                    : sheet === "account"
                      ? t("nav.account", "Account")
                      : t("nav.about", "About")}
                </h3>
                <button
                  onClick={() => setSheet(null)}
                  aria-label={t("common.close")}
                  className="rounded-full bg-teal-deep/5 p-2 text-teal-deep/60"
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
                    <li key={h.title} className="flex items-start gap-3 rounded-2xl bg-ivory/70 px-3.5 py-3">
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-mint-soft">
                        <h.icon size={15} className="text-teal-deep" strokeWidth={2.2} />
                      </div>
                      <div className="min-w-0">
                        <p className="text-xs font-extrabold text-teal-deep">{h.title}</p>
                        <p className="mt-0.5 text-[0.7rem] font-medium leading-relaxed text-teal-deep/60">{h.text}</p>
                      </div>
                    </li>
                  ))}
                </ul>
              )}

              {sheet === "account" && (
                <div className="space-y-3">
                  <div className="flex items-center gap-3 rounded-2xl bg-ivory/70 px-4 py-3.5">
                    <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-teal-deep text-base font-extrabold text-mint">
                      {(user?.name || "W")
                        .trim()
                        .split(/\s+/)
                        .slice(0, 2)
                        .map((w) => w[0]?.toUpperCase())
                        .join("")}
                    </div>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-extrabold text-teal-deep">{user?.name || "—"}</p>
                      <p className="truncate text-xs font-medium text-teal-deep/55">{t("settings.ashaWorker", "ASHA Worker")}</p>
                    </div>
                  </div>
                  <div className="space-y-1.5">
                    {[
                      [t("login.workerId"), user?.worker_id || "—"],
                      [t("common.village"), user?.phc || "—"],
                      [t("common.language"), LANGUAGES.find((l) => l.code === (user?.language || lang))?.native || "English"],
                    ].map(([k, v]) => (
                      <div key={k} className="flex items-center justify-between rounded-xl bg-ivory/70 px-4 py-2.5">
                        <span className="text-xs font-semibold text-teal-deep/55">{k}</span>
                        <span className="text-xs font-extrabold text-teal-deep">{v}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {sheet === "about" && (
                <div className="space-y-3 text-center">
                  <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-3xl bg-gradient-to-br from-pink to-violet text-white shadow-card">
                    <Radio size={28} strokeWidth={2.2} />
                  </div>
                  <p className="text-lg font-extrabold text-teal-deep">{t("app.name")}</p>
                  <p className="text-xs font-semibold uppercase tracking-wider text-pink">{t("app.tagline")}</p>
                  <p className="text-sm font-medium leading-relaxed text-teal-deep/60">
                    {t("settings.aboutDesc")}
                  </p>
                  <div className="flex items-center justify-center gap-2 pt-1">
                    <span className="chip bg-mint-soft text-teal-deep">{t("app.listen")}</span>
                    <span className="chip bg-lavender/20 text-midnight">{t("app.remember")}</span>
                    <span className="chip bg-coral/15 text-coral">{t("app.protect")}</span>
                  </div>
                  <p className="text-[0.68rem] font-semibold text-teal-deep/40">{t("settings.version", "Version 1.0.0")}</p>
                </div>
              )}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
