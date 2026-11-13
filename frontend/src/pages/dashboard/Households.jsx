import React, { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  Search,
  Home as HomeIcon,
  Users,
  X,
  Download,
  ShieldCheck,
  CalendarDays,
  CalendarClock,
  UserPlus,
} from "lucide-react";
import { api } from "../../lib/api.js";
import { showToast } from "../../components/ui/Toast.jsx";
import Empty from "../../components/ui/Empty.jsx";
import { SkeletonCard } from "../../components/ui/Skeleton.jsx";
import { useI18n } from "../../lib/i18n.jsx";

const INPUT =
  "w-full rounded-2xl border border-teal-deep/10 bg-ivory/70 px-4 py-2.5 text-sm font-medium text-teal-deep placeholder:text-teal-deep/35 focus:border-mint focus:outline-none focus:ring-2 focus:ring-mint/30";

const STATUS_KEY = {
  ok: "households.statusOk",
  overdue: "households.statusOverdue",
  upcoming: "households.statusUpcoming",
  attention: "households.statusAttention",
};

function statusChipStyle(status) {
  const s = (status || "").toLowerCase();
  if (s === "overdue") return "bg-coral/15 text-coral";
  if (s === "attention") return "bg-lavender/30 text-midnight";
  if (s === "upcoming") return "bg-lavender/20 text-midnight";
  return "bg-mint-soft text-teal-deep";
}

export default function Households() {
  const navigate = useNavigate();
  const { t } = useI18n();

  const [search, setSearch] = useState("");
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);

  const fetchList = useCallback(async (q) => {
    setLoading(true);
    try {
      const qs = q ? `?search=${encodeURIComponent(q)}` : "";
      const d = await api.get(`/households${qs}`);
      setItems(d.households || []);
    } catch (e) {
      showToast(e.message || t("households.loadErr", "Could not load households."), "error");
    } finally {
      setLoading(false);
    }
  }, []);

  const debounceRef = useRef(null);
  useEffect(() => {
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => fetchList(search), 380);
    return () => clearTimeout(debounceRef.current);
  }, [search, fetchList]);

  return (
    <div className="space-y-5">
      {/* header + search */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-extrabold text-teal-deep">{t("households.title")}</h2>
          <p className="mt-0.5 text-sm font-medium text-teal-deep/55">{t("households.subtitle")}</p>
        </div>
        <div className="flex items-center gap-2.5">
          <button
            onClick={() => navigate("/app/household-health")}
            className="btn-mint flex items-center gap-2 px-4 py-2.5 text-sm"
          >
            <UserPlus size={16} strokeWidth={2.4} />
            {t("households.new")}
          </button>
        </div>
      </div>

      <div className="card-ivory flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative w-full sm:max-w-xs">
          <Search size={16} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-teal-deep/40" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={`${t("common.search")} — ${t("common.village")}, ID…`}
            className="w-full rounded-2xl border border-teal-deep/10 bg-ivory/70 py-2.5 pl-10 pr-9 text-sm font-medium text-teal-deep placeholder:text-teal-deep/35 focus:border-mint focus:outline-none focus:ring-2 focus:ring-mint/30"
          />
          {search && (
            <button
              onClick={() => setSearch("")}
              aria-label={t("households.clearSearch", "Clear search")}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded-full p-1 text-teal-deep/40 hover:text-teal-deep"
            >
              <X size={14} />
            </button>
          )}
        </div>
      </div>

      {/* list */}
      {loading ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="card-ivory">
          <Empty
            icon={HomeIcon}
            title={t("households.title")}
            subtitle={t("empty.records")}
          />
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {items.map((h, i) => (
            <motion.button
              key={h.id}
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35, delay: Math.min(i * 0.05, 0.4), ease: "easeOut" }}
              onClick={() => navigate(`/app/households/${h.id}`)}
              className="card-ivory group p-5 text-left transition-all hover:-translate-y-0.5 hover:shadow-card focus:outline-none focus:ring-2 focus:ring-mint/50"
            >
              <div className="flex items-start gap-3.5">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-teal-deep text-mint">
                  <HomeIcon size={20} strokeWidth={2.2} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <p className="truncate text-base font-extrabold text-teal-deep">{h.village}</p>
                    <span className={`chip shrink-0 ${statusChipStyle(h.status)}`}>
                      {t(STATUS_KEY[h.status] || "households.statusOk")}
                    </span>
                  </div>
                  <p className="mt-0.5 flex items-center gap-1.5 truncate text-xs font-semibold text-teal-deep/50">
                    <Users size={12} /> {t("households.members")}: {h.member_count} · {h.address || "—"}
                  </p>
                </div>
              </div>
              <div className="mt-4 flex flex-wrap items-center gap-2">
                {h.last_visit_date && (
                  <span className="chip bg-teal-deep/5 text-teal-deep/55">
                    <CalendarDays size={11} /> {t("households.lastVisit")}: {h.last_visit_date}
                  </span>
                )}
                {h.next_followup_date && (
                  <span className="chip bg-lavender/20 text-midnight">
                    <CalendarClock size={11} /> {t("households.nextFollowup")}: {h.next_followup_date}
                  </span>
                )}
              </div>
              <p className="mt-3 truncate font-mono text-[0.68rem] font-semibold tracking-wide text-teal-deep/35">
                {h.qr_id}
              </p>
            </motion.button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ------------------------------ register modal (QR download) ------------------------------ */

export function HouseholdRegisterModal({ open, onClose, onRegistered }) {
  const { t } = useI18n();
  const [form, setForm] = useState({ village: "", address: "", member_count: "" });
  const [saving, setSaving] = useState(false);
  const [created, setCreated] = useState(null); // { id, qr_id, data_url }

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  useEffect(() => {
    if (!open) {
      setForm({ village: "", address: "", member_count: "" });
      setCreated(null);
      setSaving(false);
    }
  }, [open]);

  const submit = async (e) => {
    e.preventDefault();
    if (!form.village.trim()) {
      showToast(t("households.villageRequired", "Please enter the village name."), "warn");
      return;
    }
    setSaving(true);
    try {
      const d = await api.post("/households", {
        village: form.village.trim(),
        address: form.address.trim(),
        member_count: form.member_count ? Number(form.member_count) : 0,
      });
      const h = d.households?.[0];
      showToast(t("households.registered", "Household registered."), "success");
      onRegistered?.();
      if (h?.id) {
        setCreated(h);
        try {
          const qr = await api.get(`/households/${h.id}/qr`);
          setCreated((c) => ({ ...c, data_url: qr.data_url }));
        } catch {}
      }
    } catch (err) {
      showToast(
        err.message || t("households.registerErr", "Registration failed. Please try again."),
        "error"
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-end justify-center bg-teal-deep/50 p-0 backdrop-blur-sm sm:items-center sm:p-6"
          onClick={onClose}
        >
          <motion.div
            initial={{ y: 60, opacity: 0, scale: 0.98 }}
            animate={{ y: 0, opacity: 1, scale: 1 }}
            exit={{ y: 40, opacity: 0, scale: 0.98 }}
            transition={{ type: "spring", damping: 28, stiffness: 340 }}
            onClick={(e) => e.stopPropagation()}
            className="card-ivory max-h-[92vh] w-full max-w-md overflow-y-auto rounded-b-none p-6 sm:rounded-3xl"
          >
            {!created ? (
              <>
                <h3 className="text-lg font-extrabold text-teal-deep">{t("households.new")}</h3>
                <p className="mt-1 text-sm font-medium text-teal-deep/55">
                  {t(
                    "households.qrHint",
                    "A QR with an anonymous household ID will be generated — no personal data is stored in it."
                  )}
                </p>
                <form onSubmit={submit} className="mt-5 space-y-3.5">
                  <Field label={`${t("common.village")} *`}>
                    <input
                      value={form.village}
                      onChange={set("village")}
                      required
                      placeholder={t("households.villagePlaceholder", "e.g. Rampur")}
                      className={INPUT}
                    />
                  </Field>
                  <Field label={t("households.address", "Address")}>
                    <input
                      value={form.address}
                      onChange={set("address")}
                      placeholder={t("households.addressPlaceholder", "e.g. House 24, Ward 3")}
                      className={INPUT}
                    />
                  </Field>
                  <Field label={t("households.members")}>
                    <input
                      type="number"
                      min="0"
                      max="30"
                      value={form.member_count}
                      onChange={set("member_count")}
                      placeholder={t("households.membersPlaceholder", "e.g. 5")}
                      className={INPUT}
                    />
                  </Field>
                  <div className="flex gap-3 pt-1">
                    <button type="button" onClick={onClose}
                      className="flex-1 rounded-full bg-teal-deep/5 px-4 py-2.5 text-sm font-bold text-teal-deep/60 transition-colors hover:bg-teal-deep/10">
                      {t("common.cancel")}
                    </button>
                    <button type="submit" disabled={saving} className="btn-mint flex flex-1 items-center justify-center gap-2 px-4 py-2.5 text-sm disabled:opacity-60">
                      {t("common.save")}
                    </button>
                  </div>
                </form>
              </>
            ) : (
              <div className="text-center">
                <motion.div
                  initial={{ scale: 0.6, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  transition={{ type: "spring", damping: 14 }}
                  className="mx-auto mb-4 w-fit"
                >
                  {created.data_url ? (
                    <img src={created.data_url} alt={`QR code for ${created.qr_id}`}
                      className="mx-auto h-44 w-44 rounded-2xl border border-teal-deep/10 bg-white p-2" />
                  ) : (
                    <div className="mx-auto flex h-44 w-44 items-center justify-center rounded-2xl bg-mint-soft text-teal-deep">
                      <ShieldCheck size={40} />
                    </div>
                  )}
                </motion.div>
                <h3 className="text-lg font-extrabold text-teal-deep">{created.village}</h3>
                <p className="mt-1 font-mono text-xs font-bold tracking-wider text-teal-deep/60">{created.qr_id}</p>
                <p className="mx-auto mt-3 max-w-xs text-xs font-medium leading-relaxed text-teal-deep/55">
                  QR contains only an anonymous household ID — no personal information.
                </p>
                <div className="mt-5 flex flex-col gap-2.5">
                  {created.data_url && (
                    <a href={created.data_url} download={`${created.qr_id}.png`}
                      className="btn-mint flex items-center justify-center gap-2 px-4 py-2.5 text-sm">
                      <Download size={16} strokeWidth={2.4} /> {t("common.downloadPng")}
                    </a>
                  )}
                  <button onClick={onClose}
                    className="rounded-full bg-teal-deep/5 px-4 py-2.5 text-sm font-bold text-teal-deep/60 transition-colors hover:bg-teal-deep/10">
                    {t("common.close")}
                  </button>
                </div>
              </div>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export function Field({ label, children }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-extrabold uppercase tracking-wide text-teal-deep/50">{label}</span>
      {children}
    </label>
  );
}
