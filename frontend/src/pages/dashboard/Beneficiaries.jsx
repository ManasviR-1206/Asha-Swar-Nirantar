import React, { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  Search,
  UserPlus,
  Users,
  X,
  Download,
  FileJson,
  ShieldCheck,
  CalendarDays,
  CalendarClock,
} from "lucide-react";
import { api } from "../../lib/api.js";
import { useAuth } from "../../lib/auth.jsx";
import { showToast } from "../../components/ui/Toast.jsx";
import Empty from "../../components/ui/Empty.jsx";
import { SkeletonCard } from "../../components/ui/Skeleton.jsx";
import { useI18n } from "../../lib/i18n.jsx";
import { categoryLabel } from "../../lib/labels.js";

/* Canonical category keys — the backend stores these lowercase. */
const CATEGORIES = ["pregnancy", "newborn", "child", "immunisation", "elderly", "nutrition"];

const INPUT =
  "w-full rounded-2xl border border-teal-deep/10 bg-ivory/70 px-4 py-2.5 text-sm font-medium text-teal-deep placeholder:text-teal-deep/35 focus:border-mint focus:outline-none focus:ring-2 focus:ring-mint/30";

/** Maps a raw category key to its translation key. */
function catKey(cat) {
  return `cat.${(cat || "").toLowerCase()}`;
}

/** Human label for a category, translated when known. */
function catLabel(cat, t) {
  return categoryLabel(cat, t);
}

function statusChipStyle(status) {
  const s = (status || "").toLowerCase();
  if (s.includes("active") || s.includes("ok")) return "bg-mint-soft text-teal-deep";
  if (s.includes("overdue") || s.includes("alert") || s.includes("danger")) return "bg-coral/15 text-coral";
  if (s.includes("follow") || s.includes("due")) return "bg-lavender/20 text-midnight";
  return "bg-teal-deep/8 text-teal-deep/60";
}

function initials(name) {
  return (name || "?")
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join("");
}

/** Saves a JSON blob next to the downloadable QR card. */
function downloadJson(payload, name) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${name}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

export default function Beneficiaries() {
  const navigate = useNavigate();
  const { mode } = useAuth();
  const { t } = useI18n();
  const [searchParams, setSearchParams] = useSearchParams();

  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);

  // ?add=1 auto-opens the registration modal.
  useEffect(() => {
    if (searchParams.get("add") === "1") {
      setModalOpen(true);
      setSearchParams({}, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fetchList = useCallback(
    async (q, cat) => {
      setLoading(true);
      try {
        const params = new URLSearchParams();
        if (q) params.set("search", q);
        if (cat) params.set("category", cat);
        const qs = params.toString();
        const d = await api.get(`/beneficiaries${qs ? `?${qs}` : ""}`);
        setItems(d.beneficiaries || []);
      } catch (e) {
        showToast(e.message || t("ben.loadErr", "Could not load beneficiaries."), "error");
      } finally {
        setLoading(false);
      }
    },
    [t]
  );

  // Debounced refetch when the search term changes.
  const debounceRef = useRef(null);
  useEffect(() => {
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => fetchList(search, category), 380);
    return () => clearTimeout(debounceRef.current);
  }, [search, category, fetchList]);

  const changeCategory = (c) => {
    setCategory(c);
    clearTimeout(debounceRef.current);
    fetchList(search, c);
  };

  return (
    <div className="space-y-5">
      {/* header + search */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-extrabold text-teal-deep">{t("nav.beneficiaries")}</h2>
          <p className="mt-0.5 text-sm font-medium text-teal-deep/55">
            {t("ben.subtitle", "Every person in your care, one anonymous QR at a time.")}
          </p>
        </div>
        <div className="flex items-center gap-2.5">
          {mode === "demo" && (
            <span className="chip bg-lavender/20 text-midnight">{t("common.demoData", "Demo data")}</span>
          )}
          <button onClick={() => setModalOpen(true)} className="btn-mint flex items-center gap-2 px-4 py-2.5 text-sm">
            <UserPlus size={16} strokeWidth={2.4} />
            {t("ben.register", "Register Beneficiary")}
          </button>
        </div>
      </div>

      <div className="card-ivory flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative w-full sm:max-w-xs">
          <Search size={16} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-0.5 text-teal-deep/40" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t("ben.searchPlaceholder", "Search by name, village or ID…")}
            className="w-full rounded-2xl border border-teal-deep/10 bg-ivory/70 py-2.5 pl-10 pr-9 text-sm font-medium text-teal-deep placeholder:text-teal-deep/35 focus:border-mint focus:outline-none focus:ring-2 focus:ring-mint/30"
          />
          {search && (
            <button
              onClick={() => setSearch("")}
              aria-label={t("ben.clearSearch", "Clear search")}
              className="absolute right-2.5 top-1/2 -translate-y-0.5 rounded-full p-1 text-teal-deep/40 hover:text-teal-deep"
            >
              <X size={14} />
            </button>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => changeCategory("")}
            className={[
              "chip px-3.5 py-1.5 transition-all",
              category === ""
                ? "bg-teal-deep text-white shadow-soft"
                : "bg-teal-deep/5 text-teal-deep/60 hover:bg-mint-soft hover:text-teal-deep",
            ].join(" ")}
          >
            {t("common.all")}
          </button>
          {CATEGORIES.map((c) => (
            <button
              key={c}
              onClick={() => changeCategory(c)}
              className={[
                "chip px-3.5 py-1.5 transition-all",
                category === c
                  ? "bg-teal-deep text-white shadow-soft"
                  : "bg-teal-deep/5 text-teal-deep/60 hover:bg-mint-soft hover:text-teal-deep",
              ].join(" ")}
            >
              {t(catKey(c))}
            </button>
          ))}
        </div>
      </div>

      {/* list */}
      {loading ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="card-ivory">
          <Empty
            icon={Users}
            title={t("ben.empty", "No beneficiaries found")}
            subtitle={
              search || category
                ? t("ben.emptyFiltered", "Try a different search term or category filter.")
                : t("ben.emptyHint", "Register your first beneficiary to begin recording voice visits.")
            }
            action={
              <button onClick={() => setModalOpen(true)} className="btn-mint flex items-center gap-2 px-5 py-2.5 text-sm">
                <UserPlus size={16} strokeWidth={2.4} /> {t("ben.register", "Register Beneficiary")}
              </button>
            }
          />
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {items.map((b, i) => (
            <motion.button
              key={b.id}
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35, delay: Math.min(i * 0.05, 0.4), ease: "easeOut" }}
              onClick={() => navigate(`/app/beneficiaries/${b.id}`)}
              className="card-ivory group p-5 text-left transition-all hover:-translate-y-0.5 hover:shadow-card focus:outline-none focus:ring-2 focus:ring-mint/50"
            >
              <div className="flex items-start gap-3.5">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-teal-deep text-sm font-extrabold text-mint">
                  {initials(b.name)}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <p className="truncate text-base font-extrabold text-teal-deep">{b.name}</p>
                    <span className={`chip shrink-0 ${statusChipStyle(b.status)}`}>
                      {b.status === "ok" ? t("ben.status.active", "Active") : b.status === "danger" ? t("ben.status.danger", "Danger") : b.status === "overdue" ? t("ben.status.overdue", "Overdue") : b.status === "upcoming" ? t("ben.status.upcoming", "Upcoming") : b.status}
                    </span>
                  </div>
                  <p className="mt-0.5 flex items-center gap-1.5 truncate text-xs font-semibold text-teal-deep/50">
                    {b.age ? `${t("ben.years", "{n} yrs").replace("{n}", b.age)}` : ""} {b.age ? "·" : ""}{" "}
                    {b.village || "—"}
                  </p>
                </div>
              </div>
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <span className="chip bg-mint-soft text-teal-deep">{catLabel(b.category, t)}</span>
                {b.last_visit_date && (
                  <span className="chip bg-teal-deep/5 text-teal-deep/55">
                    <CalendarDays size={11} /> {t("ben.lastVisit", "Last")}: {b.last_visit_date}
                  </span>
                )}
                {b.next_followup_date && (
                  <span className="chip bg-lavender/20 text-midnight">
                    <CalendarClock size={11} /> {t("ben.nextFollowup", "Next")}: {b.next_followup_date}
                  </span>
                )}
              </div>
              <p className="mt-3 truncate font-mono text-[0.68rem] font-semibold tracking-wide text-teal-deep/35">
                {b.qr_id}
              </p>
            </motion.button>
          ))}
        </div>
      )}

      <RegisterModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onRegistered={() => fetchList(search, category)}
      />
    </div>
  );
}

/* ------------------------------ register modal ------------------------------ */

function RegisterModal({ open, onClose, onRegistered }) {
  const { t } = useI18n();
  const [form, setForm] = useState({ name: "", age: "", category: "pregnancy", village: "", phone: "" });
  const [saving, setSaving] = useState(false);
  const [created, setCreated] = useState(null); // { qr_id, data_url }
  const [qrLoading, setQrLoading] = useState(false);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  useEffect(() => {
    if (!open) {
      setForm({ name: "", age: "", category: "pregnancy", village: "", phone: "" });
      setCreated(null);
      setSaving(false);
    }
  }, [open]);

  const submit = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) {
      showToast(t("ben.nameRequired", "Please enter the beneficiary's name."), "warn");
      return;
    }
    setSaving(true);
    try {
      const d = await api.post("/beneficiaries", {
        name: form.name.trim(),
        age: form.age ? Number(form.age) : 0,
        category: form.category,
        village: form.village.trim() || "",
        phone: form.phone.trim() || undefined,
      });
      showToast(t("ben.registered", "{name} registered successfully.").replace("{name}", form.name.trim()), "success");
      onRegistered?.();
      // The API returns { beneficiaries: [...] } — normalise both shapes.
      const created0 = d?.beneficiary || d?.beneficiaries?.[0] || d;
      if (created0?.id) {
        const b = created0;
        setCreated(b);
        setQrLoading(true);
        try {
          const qr = await api.get(`/beneficiaries/${b.id}/qr`);
          setCreated((c) => ({ ...c, data_url: qr.data_url, qr_id: qr.qr_id || c.qr_id }));
        } catch {
          showToast(t("ben.qrLoadErr", "Could not load the QR code image."), "warn");
        } finally {
          setQrLoading(false);
        }
      }
    } catch (err) {
      showToast(err.message || t("ben.registerErr", "Registration failed. Please try again."), "error");
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
                <h3 className="text-lg font-extrabold text-teal-deep">{t("ben.register", "Register Beneficiary")}</h3>
                <p className="mt-1 text-sm font-medium text-teal-deep/55">
                  {t(
                    "ben.registerHint",
                    "A QR with an anonymous ID will be generated — no health data is stored in it."
                  )}
                </p>
                <form onSubmit={submit} className="mt-5 space-y-3.5">
                  <Field label={`${t("ben.fullName", "Full name")} *`}>
                    <input
                      value={form.name}
                      onChange={set("name")}
                      required
                      placeholder={t("ben.namePlaceholder", "e.g. Lakshmi Devi")}
                      className={INPUT}
                    />
                  </Field>
                  <div className="grid grid-cols-2 gap-3.5">
                    <Field label={t("ben.age", "Age")}>
                      <input
                        type="number"
                        min="0"
                        max="120"
                        value={form.age}
                        onChange={set("age")}
                        placeholder={t("ben.agePlaceholder", "e.g. 26")}
                        className={INPUT}
                      />
                    </Field>
                    <Field label={`${t("common.category", "Category")} *`}>
                      <select value={form.category} onChange={set("category")} className={INPUT}>
                        {CATEGORIES.map((c) => (
                          <option key={c} value={c}>
                            {t(catKey(c))}
                          </option>
                        ))}
                      </select>
                    </Field>
                  </div>
                  <Field label={t("ben.village", "Village")}>
                    <input
                      value={form.village}
                      onChange={set("village")}
                      placeholder={t("ben.villagePlaceholder", "e.g. Devanahalli")}
                      className={INPUT}
                    />
                  </Field>
                  <Field label={t("ben.phone", "Phone (optional, for reminder SMS)")}>
                    <input
                      value={form.phone}
                      onChange={set("phone")}
                      placeholder={t("ben.phonePlaceholder", "e.g. +91 98xxxxxx")}
                      className={INPUT}
                    />
                  </Field>
                  <div className="flex gap-3 pt-1">
                    <button
                      type="button"
                      onClick={onClose}
                      className="flex-1 rounded-full bg-teal-deep/5 px-4 py-2.5 text-sm font-bold text-teal-deep/60 transition-colors hover:bg-teal-deep/10"
                    >
                      {t("common.cancel")}
                    </button>
                    <button
                      type="submit"
                      disabled={saving}
                      className="btn-mint flex flex-1 items-center justify-center gap-2 px-4 py-2.5 text-sm disabled:opacity-60"
                    >
                      {saving ? t("ben.registering", "Registering…") : t("ben.registerBtn", "Register")}
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
                  {qrLoading ? (
                    <div className="skeleton mx-auto h-44 w-44 rounded-2xl" />
                  ) : created.data_url ? (
                    <img
                      src={created.data_url}
                      alt={`QR code for ${created.qr_id}`}
                      className="mx-auto h-44 w-44 rounded-2xl border border-teal-deep/10 bg-white p-2"
                    />
                  ) : (
                    <div className="mx-auto flex h-44 w-44 items-center justify-center rounded-2xl bg-mint-soft text-teal-deep">
                      <ShieldCheck size={40} />
                    </div>
                  )}
                </motion.div>
                <h3 className="text-lg font-extrabold text-teal-deep">
                  {t("ben.isRegistered", "{name} is registered").replace("{name}", created.name || form.name)}
                </h3>
                <p className="mt-1 font-mono text-xs font-bold tracking-wider text-teal-deep/60">{created.qr_id}</p>
                <p className="mx-auto mt-3 max-w-xs text-xs font-medium leading-relaxed text-teal-deep/55">
                  {t("ben.qrAnonNote", "QR contains only an anonymous beneficiary ID — no health information.")}
                </p>
                <div className="mt-5 flex flex-col gap-2.5">
                  {created.data_url && (
                    <a
                      href={created.data_url}
                      download={`${created.qr_id}.png`}
                      className="btn-mint flex items-center justify-center gap-2 px-4 py-2.5 text-sm"
                    >
                      <Download size={16} strokeWidth={2.4} /> {t("ben.downloadQr", "Download QR")}
                    </a>
                  )}
                  <button
                    onClick={() =>
                      downloadJson(
                        {
                          type: "beneficiary",
                          qr_id: created.qr_id,
                          name: created.name || form.name,
                          category: created.category || form.category,
                          village: created.village || form.village || "",
                          age: created.age ?? form.age ?? 0,
                        },
                        created.qr_id
                      )
                    }
                    className="flex items-center justify-center gap-2 rounded-full bg-teal-deep/5 px-4 py-2.5 text-sm font-bold text-teal-deep/60 transition-colors hover:bg-teal-deep/10"
                  >
                    <FileJson size={16} strokeWidth={2.4} /> {t("common.downloadJson", "Download data (JSON)")}
                  </button>
                  <button
                    onClick={onClose}
                    className="rounded-full bg-teal-deep/5 px-4 py-2.5 text-sm font-bold text-teal-deep/60 transition-colors hover:bg-teal-deep/10"
                  >
                    {t("common.done", "Done")}
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

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-extrabold uppercase tracking-wide text-teal-deep/50">{label}</span>
      {children}
    </label>
  );
}
