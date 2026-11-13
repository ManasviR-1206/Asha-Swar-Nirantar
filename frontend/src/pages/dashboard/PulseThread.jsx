import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  Baby,
  HeartPulse,
  Syringe,
  Waves,
  Mic,
  QrCode,
  Download,
  ShieldAlert,
  BellRing,
  CalendarClock,
  User,
  ChevronRight,
} from "lucide-react";
import { api } from "../../lib/api.js";
import { showToast } from "../../components/ui/Toast.jsx";
import Empty from "../../components/ui/Empty.jsx";
import { SkeletonCard } from "../../components/ui/Skeleton.jsx";
import { useI18n } from "../../lib/i18n.jsx";
import { statusLabel, categoryLabel, followupTypeLabel } from "../../lib/labels.js";

/* --------------------------- visit field chips --------------------------- */

function visitChips(structured, t) {
  const s = structured || {};
  const chips = [];
  if (s.weeks_pregnant) chips.push(`${t("pt.chip.weeks", "Weeks")}: ${s.weeks_pregnant}`);
  if (s.bp_sys && s.bp_dia) chips.push(`${t("pt.chip.bp", "BP")}: ${s.bp_sys}/${s.bp_dia}`);
  else if (s.bp_sys) chips.push(`${t("pt.chip.bp", "BP")}: ${s.bp_sys}/—`);
  if (s.weight_kg) chips.push(`${t("pt.chip.weight", "Weight")}: ${s.weight_kg} kg`);
  if (s.temperature) chips.push(`${t("pt.chip.temp", "Temp")}: ${s.temperature} °C`);
  if (s.vaccine_name) chips.push(`${t("pt.chip.vaccine", "Vaccine")}: ${s.vaccine_name}`);
  if (s.visit_date) chips.push(`${t("pt.chip.date", "Date")}: ${s.visit_date}`);
  return chips;
}

function visitIcon(category) {
  const c = (category || "").toLowerCase();
  if (c.includes("immun") || c.includes("vaccin")) return Syringe;
  if (c.includes("pregnan") || c.includes("anc")) return HeartPulse;
  return Baby;
}

function catLabel(cat, t) {
  return categoryLabel(cat, t);
}

/* ------------------------------- timeline -------------------------------- */

function ThreadLane({ title, visits, alerts, emptyText }) {
  return (
    <div>
      {title && (
        <p className="mb-3 flex items-center gap-2 text-xs font-extrabold uppercase tracking-wider text-teal-deep/50">
          <Waves size={13} className="text-mint" strokeWidth={2.4} /> {title}
        </p>
      )}
      {visits.length === 0 && alerts.length === 0 ? (
        <p className="rounded-2xl bg-ivory/80 px-4 py-5 text-center text-xs font-semibold text-teal-deep/45">
          {emptyText}
        </p>
      ) : (
        <div className="relative ml-3 space-y-4 border-l-2 border-teal-deep/10 pl-6">
          {/* interleave alerts + visits chronologically */}
          {mergeChronological(visits, alerts).map((node, i) =>
            node.kind === "alert" ? (
              <AlertNode key={`a-${node.item.id || i}`} alert={node.item} />
            ) : (
              <VisitNode key={`v-${node.item.id || i}`} visit={node.item} />
            )
          )}
        </div>
      )}
    </div>
  );
}

function mergeChronological(visits, alerts) {
  const nodes = [
    ...(visits || []).map((v) => ({ kind: "visit", item: v, t: v.visit_date || "" })),
    ...(alerts || []).map((a) => ({ kind: "alert", item: a, t: a.created_at || "" })),
  ];
  return nodes.sort((x, y) => (x.t < y.t ? 1 : x.t > y.t ? -1 : 0));
}

function VisitNode({ visit }) {
  const { t } = useI18n();
  const Icon = visitIcon(visit.category);
  const chips = visitChips(visit.structured, t);
  const isVoice = (visit.source || "").toLowerCase() === "voice";
  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-40px" }}
      transition={{ duration: 0.35 }}
      className="relative"
    >
      <span className="absolute -left-[calc(1.5rem+9px)] top-4 flex h-[18px] w-[18px] items-center justify-center rounded-full border-2 border-mint bg-white">
        <span className="h-1.5 w-1.5 rounded-full bg-mint" />
      </span>
      <div className="card-ivory p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-mint-soft">
              <Icon size={15} className="text-teal-deep" strokeWidth={2.2} />
            </div>
            <p className="text-sm font-extrabold text-teal-deep">
              {visit.visit_date || t("pt.undatedVisit", "Undated visit")}
            </p>
          </div>
          <span className={`chip ${isVoice ? "bg-mint-soft text-teal-deep" : "bg-lavender/20 text-midnight"}`}>
            {isVoice ? t("pt.voiceSource", "Voice 🎙") : t("pt.manualSource", "Manual")}
          </span>
        </div>
        {chips.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {chips.map((c) => (
              <span key={c} className="chip bg-ivory/90 text-teal-deep/65">
                {c}
              </span>
            ))}
          </div>
        )}
      </div>
    </motion.div>
  );
}

function AlertNode({ alert }) {
  const { t } = useI18n();
  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-40px" }}
      transition={{ duration: 0.35 }}
      className="relative"
    >
      <span className="absolute -left-[calc(1.5rem+9px)] top-4 flex h-[18px] w-[18px] items-center justify-center rounded-full border-2 border-coral bg-white">
        <span className="h-1.5 w-1.5 rounded-full bg-coral" />
      </span>
      <div className="rounded-3xl border border-coral/40 bg-coral/10 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="flex items-center gap-2 text-sm font-extrabold text-coral">
            <ShieldAlert size={15} strokeWidth={2.4} /> {t("pt.dangerSign", "Danger sign")} · {alert.created_at || ""}
          </p>
          <span className="chip bg-coral text-white">{alert.severity || t("alerts.severity")}</span>
        </div>
        <p className="mt-2 text-xs font-bold text-teal-deep">"{alert.phrase}"</p>
        <p className="mt-1 text-xs font-medium text-teal-deep/60">{alert.message || t("alerts.refer")}</p>
      </div>
    </motion.div>
  );
}

/* ================================= page ================================= */

export default function PulseThread() {
  const { id: routeId } = useParams();
  const navigate = useNavigate();
  const { t } = useI18n();
  const [benId, setBenId] = useState(routeId || "");
  const [list, setList] = useState(null);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(!!routeId);
  const [showQr, setShowQr] = useState(false);
  const [qr, setQr] = useState(null); // {data_url, qr_id}

  useEffect(() => setBenId(routeId || ""), [routeId]);

  // Picker list (only needed when no :id in the route).
  useEffect(() => {
    if (routeId) return;
    let alive = true;
    api
      .get("/beneficiaries")
      .then((d) => alive && setList(d.beneficiaries || []))
      .catch((e) => showToast(e.message || t("ben.loadErr", "Could not load beneficiaries."), "error"));
    return () => {
      alive = false;
    };
  }, [routeId, t]);

  // Beneficiary detail.
  useEffect(() => {
    if (!benId) return;
    let alive = true;
    setLoading(true);
    setData(null);
    setShowQr(false);
    setQr(null);
    api
      .get(`/beneficiaries/${benId}`)
      .then((d) =>
        alive &&
        setData({
          ...(d.beneficiary || {}),
          visits: d.visits || [],
          alerts: d.alerts || [],
          reminders: d.reminders || [],
          followups: d.followups || [],
        })
      )
      .catch((e) => showToast(e.message || t("pt.loadErr", "Could not load this beneficiary."), "error"))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [benId, t]);

  const toggleQr = async () => {
    const next = !showQr;
    setShowQr(next);
    if (next && !qr) {
      try {
        const d = await api.get(`/beneficiaries/${benId}/qr`);
        setQr({ data_url: d.data_url, qr_id: d.qr_id });
      } catch {
        showToast(t("ben.qrLoadErr", "Could not load the QR code image."), "warn");
        setShowQr(false);
      }
    }
  };

  // Split visits into mother / child swimlanes.
  const lanes = useMemo(() => {
    const visits = data?.visits || [];
    const mother = visits.filter((v) => /pregnan|anc/i.test(v.category || ""));
    const child = visits.filter((v) => !/pregnan|anc/i.test(v.category || ""));
    return { mother, child, both: mother.length > 0 && child.length > 0 };
  }, [data]);

  /* ------------------------------ picker view ------------------------------ */
  if (!routeId && !benId) {
    return (
      <div className="mx-auto max-w-2xl space-y-5">
        <div>
          <h2 className="text-xl font-extrabold text-teal-deep">{t("nav.pulseThread")}</h2>
          <p className="mt-0.5 text-sm font-medium text-teal-deep/55">
            {t(
              "pt.subtitle",
              "Pick a beneficiary to see her full care story — every visit, alert and reminder in one thread."
            )}
          </p>
        </div>
        {list === null ? (
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
        ) : list.length === 0 ? (
          <div className="card-ivory">
            <Empty
              icon={User}
              title={t("pt.emptyTitle", "No beneficiaries yet")}
              subtitle={t(
                "pt.emptySub",
                "Register a beneficiary first, then her pulse thread will appear here."
              )}
              action={
                <Link to="/app/beneficiaries" className="btn-mint px-5 py-2.5 text-sm">
                  {t("pt.openBeneficiaries", "Open Beneficiaries")}
                </Link>
              }
            />
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {list.map((b, i) => (
              <motion.button
                key={b.id}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: Math.min(i * 0.05, 0.3) }}
                onClick={() => navigate(`/app/beneficiaries/${b.id}`)}
                className="card-ivory flex items-center gap-3.5 p-4 text-left transition-all hover:-translate-y-0.5 hover:shadow-card"
              >
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-teal-deep text-sm font-extrabold text-mint">
                  {(b.name || "?").slice(0, 2).toUpperCase()}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-extrabold text-teal-deep">{b.name}</p>
                  <p className="truncate text-xs font-medium text-teal-deep/50">
                    {catLabel(b.category, t)} · {b.village || "—"}
                  </p>
                </div>
                <ChevronRight size={16} className="shrink-0 text-teal-deep/30" />
              </motion.button>
            ))}
          </div>
        )}
      </div>
    );
  }

  /* ------------------------------ detail view ------------------------------ */
  if (loading) {
    return (
      <div className="space-y-5">
        <SkeletonCard />
        <div className="card-ivory p-6">
          <SkeletonCard className="!border-0 !shadow-none !bg-transparent" />
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="card-ivory">
        <Empty
          icon={Waves}
          title={t("pt.notFound", "Beneficiary not found")}
          subtitle={t("pt.notFoundSub", "This record may have been removed, or the link is out of date.")}
          action={
            <Link to="/app/beneficiaries" className="btn-mint px-5 py-2.5 text-sm">
              {t("pt.backToBen", "Back to Beneficiaries")}
            </Link>
          }
        />
      </div>
    );
  }

  const followups = data.followups || [];
  const alerts = data.alerts || [];
  const reminders = data.reminders || [];

  return (
    <div className="space-y-5">
      {/* ------------------------------ header card ------------------------------ */}
      <motion.div
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="card-ivory p-5 sm:p-6"
      >
        <div className="flex flex-wrap items-start gap-4">
          <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-3xl bg-teal-deep text-lg font-extrabold text-mint">
            {(data.name || "?")
              .trim()
              .split(/\s+/)
              .slice(0, 2)
              .map((w) => w[0]?.toUpperCase())
              .join("")}
          </div>
          <div className="min-w-0 flex-1">
            <h2 className="truncate text-xl font-extrabold text-teal-deep">{data.name}</h2>
            <div className="mt-1.5 flex flex-wrap items-center gap-2">
              <span className="chip bg-mint-soft text-teal-deep">{catLabel(data.category, t)}</span>
              {data.age != null && (
                <span className="chip bg-teal-deep/5 text-teal-deep/60">
                  {t("ben.years", "{n} yrs").replace("{n}", data.age)}
                </span>
              )}
              {data.village && (
                <span className="chip bg-teal-deep/5 text-teal-deep/60">{data.village}</span>
              )}
              <span className="chip bg-teal-deep/5 font-mono text-[0.68rem] tracking-wide text-teal-deep/55">
                {data.qr_id}
              </span>
            </div>
          </div>
          <div className="flex flex-col items-end gap-2">
            <button
              onClick={toggleQr}
              className="flex items-center gap-2 rounded-full bg-teal-deep/5 px-4 py-2 text-xs font-bold text-teal-deep/70 transition-colors hover:bg-mint-soft hover:text-teal-deep"
            >
              <QrCode size={14} strokeWidth={2.2} />
              {showQr ? t("pt.hideQr", "Hide QR") : t("pt.showQr", "Show QR")}
            </button>
            <Link
              to={`/app/voice-visit?beneficiary=${data.id}`}
              className="btn-mint flex items-center gap-2 px-4 py-2 text-xs"
            >
              <Mic size={13} strokeWidth={2.4} /> {t("nav.newVoiceVisit")}
            </Link>
          </div>
        </div>
        <AnimatePresence>
          {showQr && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden"
            >
              <div className="mt-5 flex flex-wrap items-center gap-4 rounded-2xl bg-ivory/80 p-4">
                {qr?.data_url ? (
                  <img
                    src={qr.data_url}
                    alt="Beneficiary QR"
                    className="h-36 w-36 rounded-2xl border border-teal-deep/10 bg-white p-2"
                  />
                ) : (
                  <div className="skeleton h-36 w-36 rounded-2xl" />
                )}
                <div className="min-w-0">
                  <p className="font-mono text-sm font-bold tracking-wider text-teal-deep">{qr?.qr_id || data.qr_id}</p>
                  <p className="mt-1 max-w-[16rem] text-[0.7rem] font-semibold leading-relaxed text-teal-deep/50">
                    {t("ben.qrAnonNote", "QR contains only an anonymous beneficiary ID — no health information.")}
                  </p>
                  {qr?.data_url && (
                    <a
                      href={qr.data_url}
                      download={`${qr.qr_id || data.qr_id}.png`}
                      className="mt-3 inline-flex items-center gap-2 rounded-full bg-teal-deep px-4 py-2 text-xs font-bold text-mint transition-transform hover:-translate-y-0.5"
                    >
                      <Download size={13} strokeWidth={2.4} /> {t("ben.downloadQr", "Download QR")}
                    </a>
                  )}
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
        {/* ------------------------------ timeline ------------------------------ */}
        <div className="min-w-0 space-y-6">
          {lanes.mother.length === 0 && lanes.child.length === 0 && alerts.length === 0 ? (
            <div className="card-ivory">
              <Empty
                icon={Mic}
                title={t("pt.noVoiceRecords", "No voice records yet — start the first visit.")}
                subtitle={t(
                  "pt.noVoiceRecordsSub",
                  "Every visit you record by voice will appear here as a permanent, readable thread."
                )}
                action={
                  <Link
                    to={`/app/voice-visit?beneficiary=${data.id}`}
                    className="btn-mint flex items-center gap-2 px-5 py-2.5 text-sm"
                  >
                    <Mic size={15} strokeWidth={2.4} /> {t("pt.startVoiceVisit", "Start Voice Visit")}
                  </Link>
                }
              />
            </div>
          ) : (
            <>
              {lanes.both ? (
                <>
                  <div className="card-ivory p-5 sm:p-6">
                    <ThreadLane
                      title={t("pt.motherThread", "Mother's thread")}
                      visits={lanes.mother}
                      alerts={alerts.filter((a) => /pregnan|anc/i.test(a.rule_id || a.phrase || ""))}
                      emptyText={t("pt.emptyAnc", "No ANC records yet.")}
                    />
                  </div>
                  <div className="card-ivory p-5 sm:p-6">
                    <ThreadLane
                      title={t("pt.childThread", "Child's thread")}
                      visits={lanes.child}
                      alerts={alerts.filter((a) => !/pregnan|anc/i.test(a.rule_id || a.phrase || ""))}
                      emptyText={t("pt.emptyChild", "No child records yet.")}
                    />
                  </div>
                </>
              ) : (
                <div className="card-ivory p-5 sm:p-6">
                  <ThreadLane
                    title={
                      lanes.mother.length > 0
                        ? t("pt.motherThread", "Mother's thread")
                        : t("pt.careThread", "Care thread")
                    }
                    visits={[...lanes.mother, ...lanes.child]}
                    alerts={alerts}
                    emptyText={t("pt.emptyRecords", "No records yet.")}
                  />
                </div>
              )}
            </>
          )}
        </div>

        {/* ------------------------------ side panel ------------------------------ */}
        <div className="min-w-0 space-y-5">
          <SideCard
            title={t("pt.upcomingFollowups", "Upcoming Follow-ups")}
            icon={CalendarClock}
            empty={t("pt.noFollowups", "No upcoming follow-ups.")}
          >
            {followups
              .filter((f) => !/complet|done/i.test(f.status || ""))
              .slice(0, 5)
              .map((f, i) => (
                <SideRow
                  key={f.id || i}
                  title={followupTypeLabel(f.type, t) || t("pt.followupType", "Follow-up")}
                  sub={t("pt.due", "Due {date}").replace("{date}", f.due_date || "—")}
                  chip={statusLabel(f.status, t)}
                />
              ))}
          </SideCard>

          <SideCard
            title={t("pt.openAlerts", "Open Alerts")}
            icon={ShieldAlert}
            empty={t("pt.noAlerts", "No open alerts — all clear.")}
          >
            {alerts.slice(0, 4).map((a, i) => (
              <SideRow
                key={a.id || i}
                title={`"${a.phrase}"`}
                sub={(a.created_at || "").slice(0, 10)}
                chip={a.severity || t("alerts.severity")}
                coral
              />
            ))}
          </SideCard>

          <SideCard
            title={t("pt.reminders", "Reminders")}
            icon={BellRing}
            empty={t("pt.noReminders", "No reminders scheduled.")}
          >
            {reminders.slice(0, 4).map((r, i) => (
              <SideRow
                key={r.id || i}
                title={followupTypeLabel(r.type, t) || t("pt.reminderType", "Reminder")}
                sub={t("pt.due", "Due {date}").replace("{date}", r.due_date || "—")}
                chip={statusLabel(r.sms_status || r.status, t)}
              />
            ))}
          </SideCard>
        </div>
      </div>
    </div>
  );
}

function SideCard({ title, icon: Icon, empty, children }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
      className="card-ivory p-5"
    >
      <p className="mb-3 flex items-center gap-2.5 text-sm font-extrabold text-teal-deep">
        <Icon size={15} className="text-mint" strokeWidth={2.4} /> {title}
      </p>
      {React.Children.count(children) === 0 ? (
        <p className="rounded-xl bg-ivory/80 px-3 py-4 text-center text-xs font-semibold text-teal-deep/45">{empty}</p>
      ) : (
        <div className="space-y-1.5">{children}</div>
      )}
    </motion.div>
  );
}

function SideRow({ title, sub, chip, coral = false }) {
  return (
    <div className="flex items-center gap-3 rounded-xl px-2.5 py-2">
      <div className="min-w-0 flex-1">
        <p className={`truncate text-xs font-bold ${coral ? "text-coral" : "text-teal-deep"}`}>{title}</p>
        {sub && <p className="truncate text-[0.68rem] font-medium text-teal-deep/45">{sub}</p>}
      </div>
      {chip && (
        <span
          className={`chip shrink-0 ${
            coral ? "bg-coral/15 text-coral" : "bg-mint-soft text-teal-deep"
          }`}
        >
          {chip}
        </span>
      )}
    </div>
  );
}
