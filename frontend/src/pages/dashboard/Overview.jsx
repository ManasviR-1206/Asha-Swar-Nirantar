import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Users,
  Home as HomeIcon,
  ClipboardList,
  CalendarDays,
  AlarmClock,
  ShieldAlert,
  Mic,
  QrCode,
  UserPlus,
  TrendingDown,
  ArrowRight,
  CalendarClock,
  Syringe,
  HeartPulse,
  Baby,
  Activity,
  BellRing,
  Sparkles,
  Waves,
  Droplets,
  ChevronRight,
} from "lucide-react";
import { api } from "../../lib/api.js";
import { useAuth } from "../../lib/auth.jsx";
import { showToast } from "../../components/ui/Toast.jsx";
import Stat from "../../components/ui/Stat.jsx";
import Empty from "../../components/ui/Empty.jsx";
import { SkeletonCard } from "../../components/ui/Skeleton.jsx";
import { useI18n } from "../../lib/i18n.jsx";
import { activityLabel, statusLabel, categoryLabel, driftIssue, followupTypeLabel } from "../../lib/labels.js";

const CATEGORY_ICONS = {
  pregnancy: HeartPulse,
  newborn: Baby,
  child: Baby,
  immunisation: Syringe,
  household: Droplets,
  nutrition: HeartPulse,
  community: Activity,
  elderly: HeartPulse,
};

function catIcon(cat) {
  const key = Object.keys(CATEGORY_ICONS).find((k) => (cat || "").toLowerCase().includes(k));
  return CATEGORY_ICONS[key] || Activity;
}

/* --------------------------- feature cards (4) --------------------------- */

const FEATURE_CARDS = [
  {
    to: "/app/pulse-thread",
    icon: Waves,
    title: "card.pulseThread.title",
    sub: "card.pulseThread.sub",
    grad: "from-[#F078AD] to-[#E84D9B]",
  },
  {
    to: "/app/pulse-drift",
    icon: TrendingDown,
    title: "card.pulseDrift.title",
    sub: "card.pulseDrift.sub",
    grad: "from-[#8755D9] to-[#49305E]",
  },
  {
    to: "/app/alerts",
    icon: ShieldAlert,
    title: "card.danger.title",
    sub: "card.danger.sub",
    grad: "from-[#FF806F] to-[#E84D9B]",
  },
  {
    to: "/app/reminders",
    icon: BellRing,
    title: "card.reminders.title",
    sub: "card.reminders.sub",
    grad: "from-[#BBA6FF] to-[#8755D9]",
  },
];

function WidgetCard({ title, icon: Icon, children, className = "", accent = "text-teal-deep" }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
      className={`card-ivory p-5 ${className}`}
    >
      <div className="mb-4 flex items-center gap-2.5">
        <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-mint-soft">
          <Icon size={16} className={accent} strokeWidth={2.2} />
        </div>
        <h2 className="text-sm font-extrabold text-teal-deep">{title}</h2>
      </div>
      {children}
    </motion.div>
  );
}

function Row({ title, sub, icon: Icon, chip, href }) {
  const inner = (
    <div className="flex items-center gap-3 rounded-xl px-2 py-2 transition-colors hover:bg-mint-soft/60">
      {Icon && <Icon size={15} className="shrink-0 text-teal-deep/50" strokeWidth={2.2} />}
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-bold text-teal-deep">{title}</p>
        {sub && <p className="truncate text-xs font-medium text-teal-deep/50">{sub}</p>}
      </div>
      {chip && (
        <span className="chip shrink-0 bg-mint-soft text-teal-deep">{chip}</span>
      )}
    </div>
  );
  return href ? (
    <Link to={href} className="block">
      {inner}
    </Link>
  ) : (
    inner
  );
}

function ListOrEmpty({ items, emptyText, render }) {
  if (!items || items.length === 0) {
    return (
      <div className="rounded-xl bg-ivory/70 px-3 py-5 text-center text-xs font-semibold text-teal-deep/45">
        {emptyText}
      </div>
    );
  }
  return <div className="space-y-0.5">{items.slice(0, 5).map(render)}</div>;
}

export default function Overview() {
  const { user, mode } = useAuth();
  const navigate = useNavigate();
  const { t } = useI18n();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [households, setHouseholds] = useState([]);
  const [drift, setDrift] = useState([]);
  const [liveConnected, setLiveConnected] = useState(false);

  const loadData = () => {
    api
      .get("/dashboard")
      .then((d) => setData(d))
      .catch((e) => showToast(e.message || t("dash.loadErr", "Could not load the dashboard."), "error"))
      .finally(() => setLoading(false));
    api.get("/households").then((d) => setHouseholds(d.households || [])).catch(() => {});
    api.get("/drift").then((d) => setDrift(d.items || [])).catch(() => {});
  };

  useEffect(() => {
    loadData();

    // Connect to real-time Server-Sent Events (SSE) stream
    let eventSource = null;
    try {
      eventSource = new EventSource("/api/dashboard/events");
      eventSource.onopen = () => {
        setLiveConnected(true);
      };
      eventSource.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (
            payload.type === "new_visit" ||
            payload.type === "new_household_visit" ||
            payload.type === "batch_visits_saved" ||
            payload.type === "new_beneficiary"
          ) {
            // Live update triggered by database event!
            loadData();
          }
        } catch {}
      };
      eventSource.onerror = () => {
        setLiveConnected(false);
      };
    } catch {
      setLiveConnected(false);
    }

    return () => {
      if (eventSource) {
        eventSource.close();
      }
    };
  }, []);

  const stats = data?.stats || {};
  const reminders = data?.reminders || [];
  const vaccReminders = reminders.filter((r) => /vaccin|immun/i.test(r.type || ""));
  const nutritionFups = drift.filter((d) => /nutrition/i.test(d.issue || ""));
  const alerts = data?.alerts || [];
  const hhAttention = households.filter((h) => h.status === "overdue" || h.status === "attention");

  const greetingKey =
    new Date().getHours() < 12
      ? "dash.goodMorning"
      : new Date().getHours() < 17
        ? "dash.goodAfternoon"
        : "dash.goodEvening";

  return (
    <div className="space-y-6">
      {/* ------------------------------ greeting banner ------------------------------ */}
      <motion.div
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, ease: "easeOut" }}
        className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-teal-deep to-midnight p-6 shadow-glass sm:p-7"
      >
        <div className="pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full bg-mint/20 blur-3xl" />
        <div className="relative flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="section-eyebrow text-mint">{t("app.tagline")}</p>
            <h1 className="mt-1.5 text-xl font-extrabold text-white sm:text-2xl">
              {t(greetingKey)}! {t("dash.welcome")}
            </h1>
            <p className="mt-1.5 text-sm font-medium text-white/60">{t("dash.welcomeSub")}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {liveConnected && (
              <span className="chip border border-mint/30 bg-mint/20 text-xs font-bold text-mint">
                <span className="mr-1 inline-block h-1.5 w-1.5 animate-ping rounded-full bg-mint" />
                Live Sync
              </span>
            )}
            {mode === "demo" && (
              <span className="chip bg-white/10 text-mint">
                <Sparkles size={12} /> {t("common.syntheticData")}
              </span>
            )}
          </div>
        </div>
      </motion.div>

      {/* ------------------------------ stat cards ------------------------------ */}
      {loading ? (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
          {Array.from({ length: 6 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
          <Stat label={t("stat.totalHouseholds")} value={stats.total_households} icon={HomeIcon} tone="lavender" delay={0} />
          <Stat label={t("stat.totalBeneficiaries")} value={stats.total_beneficiaries} icon={Users} tone="mint" delay={0.04} />
          <Stat label={t("stat.todaysVisits")} value={stats.todays_visits} icon={ClipboardList} tone="teal" delay={0.08} />
          <Stat label={t("stat.upcomingFollowups")} value={stats.upcoming_followups} icon={CalendarDays} tone="lavender" delay={0.12} />
          <Stat
            label={t("stat.overdueFollowups")}
            value={stats.overdue_followups}
            icon={AlarmClock}
            tone={stats.overdue_followups > 0 ? "coral" : "mint"}
            delay={0.16}
          />
          <Stat
            label={t("stat.activeAlerts")}
            value={stats.active_alerts}
            icon={ShieldAlert}
            tone={stats.active_alerts > 0 ? "coral" : "mint"}
            delay={0.2}
          />
        </div>
      )}

      {/* ------------------------------ 4 feature cards ------------------------------ */}
      <div>
        <h2 className="mb-3 text-sm font-extrabold uppercase tracking-wider text-teal-deep/60">
          {t("section.features")}
        </h2>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {FEATURE_CARDS.map((f, i) => {
            const Icon = f.icon;
            return (
              <motion.button
                key={f.to}
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.05 * i, duration: 0.4, ease: "easeOut" }}
                onClick={() => navigate(f.to)}
                className="group relative overflow-hidden rounded-3xl bg-white p-5 text-left shadow-soft transition-all hover:-translate-y-1 hover:shadow-card focus:outline-none focus:ring-2 focus:ring-mint/50"
              >
                <div
                  className={`absolute -right-8 -top-8 h-28 w-28 rounded-full bg-gradient-to-br ${f.grad} opacity-20 blur-2xl transition-opacity group-hover:opacity-40`}
                />
                <div className={`relative mb-4 flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br ${f.grad} text-white shadow-[0_8px_20px_rgba(232,77,155,0.35)]`}>
                  <Icon size={20} strokeWidth={2.2} />
                </div>
                <h3 className="relative text-base font-extrabold text-teal-deep">{t(f.title)}</h3>
                <p className="relative mt-1.5 text-xs font-medium leading-relaxed text-teal-deep/55">{t(f.sub)}</p>
                <span className="relative mt-3 inline-flex items-center gap-1 text-xs font-extrabold text-pink">
                  {t("common.view")} <ChevronRight size={13} className="transition-transform group-hover:translate-x-0.5" />
                </span>
              </motion.button>
            );
          })}
        </div>
      </div>

      {/* ------------------------------ widgets grid ------------------------------ */}
      {loading ? (
        <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : (
        <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
          {/* Today's visit schedule */}
          <WidgetCard title={t("section.schedule")} icon={CalendarClock}>
            <ListOrEmpty
              items={data?.schedule}
              emptyText={t("reminders.empty")}
              render={(s, i) => (
                <Row
                  key={i}
                  icon={CalendarClock}
                  title={s.beneficiary_name}
                  sub={`${s.time} · ${s.village || ""}`}
                  chip={followupTypeLabel(s.type, t)}
                />
              )}
            />
          </WidgetCard>

          {/* Recent activity */}
          <WidgetCard title={t("section.recentActivity")} icon={Activity}>
            <ListOrEmpty
              items={data?.recent_activity}
              emptyText={t("empty.records")}
              render={(a, i) => {
                const Icon = catIcon(a.category);
                return (
                  <Row
                    key={i}
                    icon={Icon}
                    title={a.beneficiary_name}
                    sub={`${activityLabel(a, t)} · ${a.date}`}
                    chip={categoryLabel(a.category, t)}
                  />
                );
              }}
            />
          </WidgetCard>

          {/* Household Health Overview */}
          <WidgetCard title={t("section.householdOverview")} icon={Droplets}>
            <ListOrEmpty
              items={hhAttention.length > 0 ? hhAttention : households}
              emptyText={t("empty.records")}
              render={(h, i) => (
                <Row
                  key={h.id}
                  icon={HomeIcon}
                  title={h.village}
                  sub={`${h.qr_id} · ${t("households.lastVisit")}: ${h.last_visit_date || "—"}`}
                  chip={t(`households.status${(h.status || "ok").charAt(0).toUpperCase()}${(h.status || "ok").slice(1)}`)}
                  href={`/app/households/${h.id}`}
                />
              )}
            />
            <Link
              to="/app/households"
              className="mt-3 flex items-center justify-center gap-1.5 rounded-xl bg-mint/10 px-3 py-2 text-xs font-extrabold text-pink transition-colors hover:bg-mint/20"
            >
              {t("nav.households")} <ArrowRight size={13} />
            </Link>
          </WidgetCard>

          {/* Danger-sign alert panel */}
          <WidgetCard title={t("section.activeAlerts")} icon={ShieldAlert} accent="text-coral">
            {alerts.length === 0 ? (
              <div className="rounded-xl bg-mint-soft/60 px-3 py-5 text-center text-xs font-semibold text-teal-deep/60">
                {t("alerts.empty")}
              </div>
            ) : (
              <>
                <div className="space-y-0.5">
                  {alerts.slice(0, 3).map((a) => (
                    <Row
                      key={a.id}
                      icon={ShieldAlert}
                      title={a.beneficiary_name}
                      sub={`"${a.phrase}"`}
                      chip={a.severity}
                      href="/app/alerts"
                    />
                  ))}
                </div>
                <Link
                  to="/app/alerts"
                  className="mt-3 flex items-center justify-center gap-1.5 rounded-xl bg-coral/10 px-3 py-2 text-xs font-extrabold text-coral transition-colors hover:bg-coral/20"
                >
                  {t("common.view")} <ArrowRight size={13} />
                </Link>
              </>
            )}
          </WidgetCard>

          {/* Nutrition follow-ups */}
          <WidgetCard title={t("section.nutritionFollowups")} icon={HeartPulse}>
            <ListOrEmpty
              items={nutritionFups}
              emptyText={t("drift.empty")}
              render={(d, i) => (
                <Row
                  key={i}
                  icon={HeartPulse}
                  title={d.name}
                  sub={driftIssue(d, t)}
                  chip={d.overdue_days > 0 ? t("drift.overdueBy", "").replace("{n}", d.overdue_days) : categoryLabel(d.category, t)}
                  href={d.household_id ? `/app/households/${d.household_id}` : `/app/beneficiaries/${d.beneficiary_id}`}
                />
              )}
            />
            <Link
              to="/app/pulse-drift"
              className="mt-3 flex items-center justify-center gap-1.5 rounded-xl bg-mint/10 px-3 py-2 text-xs font-extrabold text-pink transition-colors hover:bg-mint/20"
            >
              {t("nav.pulseDrift")} <ArrowRight size={13} />
            </Link>
          </WidgetCard>

          {/* Upcoming vaccination reminders */}
          <WidgetCard title={t("section.vaccinationReminders")} icon={Syringe}>
            <ListOrEmpty
              items={vaccReminders}
              emptyText={t("reminders.empty")}
              render={(r) => (
                <Row
                  key={r.id}
                  icon={Syringe}
                  title={r.beneficiary_name}
                  sub={`${t("drift.dueDate")}: ${r.due_date || "—"}`}
                  chip={statusLabel(r.sms_status || r.type, t)}
                  href="/app/reminders"
                />
              )}
            />
          </WidgetCard>

          {/* Upcoming SMS reminders */}
          <WidgetCard title={t("section.smsReminders")} icon={BellRing}>
            <ListOrEmpty
              items={reminders}
              emptyText={t("reminders.empty")}
              render={(r) => (
                <Row
                  key={r.id}
                  icon={BellRing}
                  title={r.beneficiary_name}
                  sub={`${t("drift.dueDate")}: ${r.due_date || "—"}`}
                  chip={statusLabel(r.sms_status || r.type, t)}
                  href="/app/reminders"
                />
              )}
            />
          </WidgetCard>

          {/* Recent voice records */}
          <WidgetCard title={t("voice.title")} icon={Mic}>
            <ListOrEmpty
              items={data?.recent_voice}
              emptyText={t("empty.records")}
              render={(v, i) => (
                <Row
                  key={i}
                  icon={Mic}
                  title={v.beneficiary_name}
                  sub={`${v.date} · ${(v.language || "").toUpperCase()}`}
                  chip={statusLabel(v.status, t)}
                  href="/app/pulse-thread"
                />
              )}
            />
          </WidgetCard>

          {/* Quick actions */}
          <WidgetCard title={t("section.quickVoice")} icon={Sparkles}>
            <div className="grid grid-cols-2 gap-2.5">
              <QuickAction icon={Mic} label={t("nav.newVoiceVisit")} to="/app/voice-visit" primary />
              <QuickAction icon={QrCode} label={t("nav.qrScanner")} to="/app/qr-scanner" />
              <QuickAction icon={UserPlus} label={t("households.new")} to="/app/household-health" />
              <QuickAction icon={TrendingDown} label={t("nav.pulseDrift")} to="/app/pulse-drift" />
            </div>
          </WidgetCard>
        </div>
      )}
    </div>
  );
}

function QuickAction({ icon: Icon, label, to, primary = false }) {
  return (
    <Link
      to={to}
      className={[
        "flex flex-col items-center gap-2 rounded-2xl px-2 py-4 text-center text-[0.72rem] font-extrabold transition-all",
        primary
          ? "btn-mint text-[0.72rem]"
          : "bg-ivory/80 text-teal-deep/75 hover:bg-mint-soft hover:text-teal-deep",
      ].join(" ")}
    >
      <Icon size={19} strokeWidth={2.2} />
      <span className="leading-tight">{label}</span>
    </Link>
  );
}
