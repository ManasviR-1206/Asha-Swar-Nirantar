import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Activity, AlarmClock, ArrowRight, Baby, BellRing, CalendarClock, CalendarDays,
  CheckCircle2, ChevronRight, ClipboardList, HeartPulse, Home as HomeIcon,
  MapPin, Mic, QrCode, ShieldAlert, Syringe, Users, Waves, TrendingDown,
} from "lucide-react";
import { api } from "../../lib/api.js";
import { showToast } from "../../components/ui/Toast.jsx";
import Stat from "../../components/ui/Stat.jsx";
import { SkeletonCard } from "../../components/ui/Skeleton.jsx";
import { useI18n } from "../../lib/i18n.jsx";
import { categoryLabel, driftIssue, followupTypeLabel, statusLabel } from "../../lib/labels.js";

function WidgetCard({ title, icon: Icon, children, className = "", accent = "text-[#7A1638]" }) {
  return (
    <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} className={`card-ivory p-5 ${className}`}>
      <div className="mb-4 flex items-center gap-2.5">
        <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-[#F4DCE4]">
          <Icon size={16} className={accent} strokeWidth={2.2} />
        </div>
        <h2 className="text-sm font-extrabold text-[#2B1F26]">{title}</h2>
      </div>
      {children}
    </motion.div>
  );
}

function Row({ title, sub, icon: Icon, chip, href, chipClass = "bg-[#F4DCE4] text-[#7A1638]" }) {
  const inner = (
    <div className="flex items-center gap-3 rounded-xl px-2 py-2 transition-colors hover:bg-[#F4DCE4]/30">
      {Icon && <Icon size={15} className="shrink-0 text-[#7A1638]/60" strokeWidth={2.2} />}
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-bold text-[#2B1F26]">{title}</p>
        {sub && <p className="truncate text-xs font-medium text-[#685B62]">{sub}</p>}
      </div>
      {chip && <span className={`chip shrink-0 ${chipClass}`}>{chip}</span>}
    </div>
  );
  return href ? <Link to={href} className="block">{inner}</Link> : inner;
}

function ListOrEmpty({ items, emptyText, render }) {
  if (!items || items.length === 0) {
    return <div className="rounded-xl bg-[#FFF7F0] px-3 py-5 text-center text-xs font-semibold text-[#685B62] border border-[#EADCE1]">{emptyText}</div>;
  }
  return <div className="space-y-0.5">{items.slice(0, 5).map(render)}</div>;
}

export default function Overview() {
  const navigate = useNavigate();
  const { t } = useI18n();
  const [data, setData] = useState(null);
  const [households, setHouseholds] = useState([]);
  const [drift, setDrift] = useState([]);
  const [modules, setModules] = useState(null);
  const [loading, setLoading] = useState(true);
  const [liveConnected, setLiveConnected] = useState(false);
  const [loadError, setLoadError] = useState("");
  const loadInFlightRef = useRef(false);
  const errorToastRef = useRef("");

  const loadData = () => {
    if (loadInFlightRef.current) return;
    loadInFlightRef.current = true;
    setLoadError("");
    Promise.allSettled([
      api.get("/dashboard"),
      api.get("/households"),
      api.get("/drift"),
      api.get("/dashboard/modules"),
    ]).then(([d, h, dr, m]) => {
      const errors = [];
      if (d.status === "fulfilled") setData(d.value); else errors.push(d.reason?.message || "dashboard");
      if (h.status === "fulfilled") setHouseholds(h.value?.households || []);
      if (dr.status === "fulfilled") setDrift(dr.value?.items || []);
      if (m.status === "fulfilled") setModules(m.value);
      if (errors.length && d.status !== "fulfilled") {
        const msg = errors[0];
        setLoadError(msg);
        if (errorToastRef.current !== msg) {
          errorToastRef.current = msg;
          showToast(t("dash.loadError"), "error");
        }
      } else {
        errorToastRef.current = "";
      }
    }).finally(() => {
      loadInFlightRef.current = false;
      setLoading(false);
    });
  };

  useEffect(() => {
    loadData();
    let es = null;
    try {
      const token = localStorage.getItem("asn_auth") ? JSON.parse(localStorage.getItem("asn_auth") || "null")?.token : null;
      const url = token ? `/api/dashboard/events?token=${encodeURIComponent(token)}` : "/api/dashboard/events";
      es = new EventSource(url);
      es.onopen = () => setLiveConnected(true);
      es.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (["new_visit", "new_household_visit", "batch_visits_saved", "new_beneficiary"].includes(payload.type)) loadData();
        } catch {}
      };
      es.onerror = () => setLiveConnected(false);
    } catch { setLiveConnected(false); }
    return () => { if (es) es.close(); };
  }, []);

  const stats = data?.asha_beneficiary_statistics || data?.stats || {};
  const alerts = data?.alerts || [];
  const reminders = data?.reminders || [];
  const schedule = data?.schedule || [];
  const recentActivity = data?.recent_activity || [];

  const todayLabel = new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "short", year: "numeric" });

  const careOverview = useMemo(() => {
    const items = drift || [];
    const byCat = (pred) => items.filter(pred);
    const maternal = byCat((d) => /preg|anc|maternal/i.test(`${d.category || ""} ${d.type || ""} ${d.issue || ""}`));
    const newborn = byCat((d) => /newborn|neonat|pnc|infant/i.test(`${d.category || ""} ${d.type || ""} ${d.issue || ""}`));
    const immun = byCat((d) => /immun|vaccin/i.test(`${d.category || ""} ${d.type || ""} ${d.issue || ""}`));
    return { maternal, newborn, immunisation: immun };
  }, [drift]);

  const priorityAttention = useMemo(() => {
    const overdueFollowups = drift.filter((d) => (d.overdue_days || 0) > 0 || /overdue|missed/i.test(d.status || ""));
    const unverified = drift.filter((d) => /unverified|verify|pending identity/i.test(`${d.issue || ""} ${d.status || ""}`));
    const pendingIdentity = modules?.voice_visits?.pending_identity || 0;
    return { overdueFollowups, unverified, pendingIdentity };
  }, [drift, modules]);

  const visitsCompleted = stats.todays_visits ?? 0;
  const visitsPending = Math.max(0, (stats.upcoming_followups ?? 0) + (stats.due_followups ?? 0)); // proxy from due/upcoming
  const pendingReferrals = alerts.filter((a) => /refer|escalat/i.test(`${a.message || ""} ${a.status || ""}`)).length;

  return (
    <div className="space-y-6">
      <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-[#7A1638] to-[#321321] p-6 shadow-card sm:p-7">
        <div className="pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full bg-[#E8A8B8]/20 blur-3xl" />
        <div className="relative flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-extrabold uppercase tracking-[0.18em] text-[#E8A8B8]">{t("app.name")}</p>
            <h1 className="mt-1.5 text-xl font-extrabold text-white sm:text-2xl">{t("dash.dailyFieldWork")}</h1>
            <p className="mt-1.5 text-sm font-medium text-white/70">{todayLabel} · {t("dash.dailyFieldWorkSub")}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {liveConnected && <span className="chip border border-[#E8A8B8]/30 bg-[#E8A8B8]/20 text-xs font-bold text-[#FFF7F0]"><span className="mr-1 inline-block h-1.5 w-1.5 animate-ping rounded-full bg-[#E8A8B8]" />{t("common.live")}</span>}
            <button onClick={() => navigate("/app/voice-visit")} className="btn-mint flex items-center gap-2 px-4 py-2 text-sm"><Mic size={15} />{t("nav.newVoiceVisit")}</button>
          </div>
        </div>
      </motion.div>

      {loading ? (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">{Array.from({ length: 8 }).map((_, i) => <SkeletonCard key={i} />)}</div>
      ) : loadError && !data ? (
        <div className="card-ivory p-6 text-center">
          <p className="text-sm font-extrabold text-[#2B1F26]">{t("dash.loadError")}</p>
          <p className="mt-1 text-xs text-[#685B62]">{loadError}</p>
          <button onClick={() => { setLoading(true); loadData(); }} className="btn-mint mt-4 px-4 py-2 text-sm">{t("common.retry")}</button>
        </div>
      ) : (
        <>
          <section className="space-y-3">
            <h2 className="text-xs font-extrabold uppercase tracking-wider text-[#685B62]">{t("dash.todayActivities")}</h2>
            <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
              <Stat label={t("dash.visitsCompletedToday")} value={visitsCompleted} icon={ClipboardList} tone="mint" />
              <Stat label={t("dash.visitsPending")} value={visitsPending} icon={CalendarDays} tone="lavender" />
              <Stat label={t("stat.upcomingFollowups", "Upcoming follow-ups")} value={stats.upcoming_followups ?? 0} icon={CalendarClock} tone="teal" />
              <Stat label={t("dash.pendingReferralsAlerts")} value={pendingReferrals || (stats.active_alerts ?? 0)} icon={ShieldAlert} tone={(pendingReferrals || stats.active_alerts) ? "coral" : "mint"} />
            </div>
          </section>

          <section className="space-y-3">
            <h2 className="text-xs font-extrabold uppercase tracking-wider text-[#685B62]">{t("dash.careOverview")}</h2>
            <div className="grid gap-4 md:grid-cols-3">
              <WidgetCard title={t("dash.maternalFollowups")} icon={HeartPulse}>
                <ListOrEmpty items={careOverview.maternal} emptyText={t("dash.noMaternal")} render={(d, i) => <Row key={i} icon={HeartPulse} title={d.name} sub={driftIssue(d, t)} chip={d.overdue_days > 0 ? `${t("common.overdue")} ${d.overdue_days}d` : t("common.upcoming")} href={d.household_id ? `/app/households/${d.household_id}` : `/app/beneficiaries/${d.beneficiary_id}`} chipClass={d.overdue_days > 0 ? "bg-red-100 text-red-700" : "bg-[#F4DCE4] text-[#7A1638]"} />} />
              </WidgetCard>
              <WidgetCard title={t("dash.newbornFollowups")} icon={Baby}>
                <ListOrEmpty items={careOverview.newborn} emptyText={t("dash.noNewborn")} render={(d, i) => <Row key={i} icon={Baby} title={d.name} sub={driftIssue(d, t)} chip={d.overdue_days > 0 ? `${t("common.overdue")} ${d.overdue_days}d` : t("common.upcoming")} href={d.household_id ? `/app/households/${d.household_id}` : `/app/beneficiaries/${d.beneficiary_id}`} chipClass={d.overdue_days > 0 ? "bg-red-100 text-red-700" : "bg-[#F4DCE4] text-[#7A1638]"} />} />
              </WidgetCard>
              <WidgetCard title={t("dash.immunisationFollowups")} icon={Syringe}>
                <ListOrEmpty items={careOverview.immunisation} emptyText={t("dash.noImmunisation")} render={(d, i) => <Row key={i} icon={Syringe} title={d.name} sub={driftIssue(d, t)} chip={d.overdue_days > 0 ? `${t("common.overdue")} ${d.overdue_days}d` : t("common.upcoming")} href={d.household_id ? `/app/households/${d.household_id}` : `/app/beneficiaries/${d.beneficiary_id}`} chipClass={d.overdue_days > 0 ? "bg-red-100 text-red-700" : "bg-[#F4DCE4] text-[#7A1638]"} />} />
              </WidgetCard>
            </div>
          </section>

          <section className="space-y-3">
            <h2 className="text-xs font-extrabold uppercase tracking-wider text-[#685B62]">{t("dash.priorityAttention")}</h2>
            <div className="grid gap-4 md:grid-cols-2">
              <WidgetCard title={t("dash.overdueFollowups")} icon={AlarmClock} accent="text-red-600">
                <ListOrEmpty items={priorityAttention.overdueFollowups} emptyText={t("dash.noOverdue")} render={(d, i) => <Row key={i} icon={AlarmClock} title={d.name} sub={driftIssue(d, t)} chip={`${d.overdue_days || 0}d`} href={d.household_id ? `/app/households/${d.household_id}` : `/app/beneficiaries/${d.beneficiary_id}`} chipClass="bg-red-100 text-red-700" />} />
                <Link to="/app/pulse-drift" className="mt-3 flex items-center justify-center gap-1.5 rounded-xl bg-[#F4DCE4]/50 px-3 py-2 text-xs font-extrabold text-[#7A1638] hover:bg-[#F4DCE4]">{t("dash.openPulseDrift")} <ArrowRight size={13} /></Link>
              </WidgetCard>
              <WidgetCard title={t("dash.recordsNeedingVerification")} icon={ClipboardList}>
                <div className="space-y-2">
                  <div className="rounded-xl border border-[#EADCE1] bg-[#FFF7F0] px-3 py-3 text-sm text-[#2B1F26]">
                    <div className="flex items-center justify-between"><span className="font-semibold text-[#685B62]">{t("dash.pendingVoiceIdentity")}</span><span className="font-extrabold">{priorityAttention.pendingIdentity}</span></div>
                  </div>
                  <ListOrEmpty items={priorityAttention.unverified} emptyText={t("dash.noUnverified")} render={(d, i) => <Row key={i} icon={ClipboardList} title={d.name} sub={d.issue || t("common.verify")} chip={t("common.verify")} href={d.household_id ? `/app/households/${d.household_id}` : `/app/beneficiaries/${d.beneficiary_id}`} />} />
                </div>
              </WidgetCard>
            </div>
          </section>

          <section className="space-y-3">
            <h2 className="text-xs font-extrabold uppercase tracking-wider text-[#685B62]">{t("dash.recentActivityTitle")}</h2>
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              <WidgetCard title={t("dash.recentHouseholdVisits")} icon={HomeIcon}>
                <ListOrEmpty items={recentActivity.filter((a) => /household/i.test(a.category || "") || /household/i.test(a.action_code || ""))} emptyText={t("dash.noHouseholdVisits")} render={(a, i) => <Row key={i} icon={HomeIcon} title={a.beneficiary_name} sub={`${a.action} · ${a.date}`} chip={categoryLabel(a.category, t)} />} />
              </WidgetCard>
              <WidgetCard title={t("dash.recentBeneficiaryRecords")} icon={Activity}>
                <ListOrEmpty items={recentActivity.filter((a) => !/household/i.test(a.category || ""))} emptyText={t("dash.noBeneficiaryRecords")} render={(a, i) => <Row key={i} icon={Activity} title={a.beneficiary_name} sub={`${a.action} · ${a.date}`} chip={categoryLabel(a.category, t)} />} />
              </WidgetCard>
              <WidgetCard title={t("dash.upcomingSchedule")} icon={CalendarClock}>
                <ListOrEmpty items={schedule} emptyText={t("dash.noSchedule")} render={(s, i) => <Row key={i} icon={CalendarClock} title={s.beneficiary_name} sub={`${s.time || ""} ${s.village ? `· ${s.village}` : ""} ${s.due_date ? `· ${s.due_date}` : ""}`} chip={followupTypeLabel(s.type, t)} />} />
                <Link to="/app/reminders" className="mt-3 flex items-center justify-center gap-1.5 rounded-xl bg-[#F4DCE4]/50 px-3 py-2 text-xs font-extrabold text-[#7A1638] hover:bg-[#F4DCE4]">{t("dash.openSmartReminders")} <ArrowRight size={13} /></Link>
              </WidgetCard>
            </div>
          </section>

          <section className="card-ivory p-4">
            <div className="flex flex-wrap items-center gap-2 text-xs font-semibold text-[#685B62]">
              <CheckCircle2 size={14} className="text-[#7A1638]" />
              {t("dash.dataIntegrityNote")}
              <div className="ml-auto flex flex-wrap gap-2">
                <Link to="/app/households" className="chip bg-[#F4DCE4] text-[#7A1638]">{t("nav.households")}</Link>
                <Link to="/app/geopulse" className="chip bg-[#F4DCE4] text-[#7A1638]">{t("nav.geopulse")}</Link>
                <Link to="/app/pulse-drift" className="chip bg-[#F4DCE4] text-[#7A1638]">{t("nav.pulseDrift")}</Link>
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  );
}