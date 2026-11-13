import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import QrScanner from "qr-scanner";
import {
  QrCode,
  ScanLine,
  Camera,
  CameraOff,
  CheckCircle2,
  XCircle,
  Mic,
  RotateCcw,
  ShieldCheck,
  Lightbulb,
  Hand,
  CreditCard,
  Home as HomeIcon,
  Users,
  Download,
  FileJson,
} from "lucide-react";
import { api } from "../../lib/api.js";
import { showToast } from "../../components/ui/Toast.jsx";
import Empty from "../../components/ui/Empty.jsx";
import { useI18n } from "../../lib/i18n.jsx";
import { categoryLabel } from "../../lib/labels.js";

const INPUT =
  "w-full rounded-2xl border border-teal-deep/10 bg-ivory/70 px-4 py-2.5 text-sm font-medium text-teal-deep placeholder:text-teal-deep/35 focus:border-mint focus:outline-none focus:ring-2 focus:ring-mint/30";

function initials(name) {
  return (name || "?")
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join("");
}

/** Household QR ids look like HN-XXXX-XXXX. */
function isHouseholdId(id) {
  return /^HN-/i.test(id);
}

export default function QRScanner() {
  const navigate = useNavigate();
  const { t } = useI18n();

  const videoRef = useRef(null);
  const scannerRef = useRef(null);

  const [cameraOn, setCameraOn] = useState(false);
  const [camError, setCamError] = useState(null); // {title, detail}
  const [hasCamera, setHasCamera] = useState(true);
  const [phase, setPhase] = useState("idle"); // idle | scanning | decoding | found | invalid
  const [ben, setBen] = useState(null);
  const [household, setHousehold] = useState(null);
  const [manualId, setManualId] = useState("");

  // QR generator state (demo records)
  const [genBen, setGenBen] = useState(null);
  const [genHh, setGenHh] = useState(null);
  const [genLoading, setGenLoading] = useState(false);

  // Check for a camera once.
  useEffect(() => {
    QrScanner.hasCamera()
      .then((ok) => setHasCamera(!!ok))
      .catch(() => setHasCamera(false));
    return () => stopCamera();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const stopCamera = () => {
    try {
      scannerRef.current?.stop();
      scannerRef.current?.destroy();
    } catch {}
    scannerRef.current = null;
    setCameraOn(false);
  };

  const startCamera = async () => {
    setCamError(null);
    setBen(null);
    setHousehold(null);
    setPhase("scanning");
    try {
      if (!videoRef.current) return;
      const s = new QrScanner(videoRef.current, handleDecode, {
        highlightScanRegion: false,
        highlightCodeOutline: false,
        returnDetailedScanResult: false,
      });
      scannerRef.current = s;
      await s.start();
      setCameraOn(true);
    } catch (e) {
      setPhase("idle");
      stopCamera();
      const msg = (e?.message || "").toLowerCase();
      setCamError(
        msg.includes("permission") || msg.includes("denied") || msg.includes("notallowed")
          ? {
              title: t("qr.cameraDeniedTitle", "Camera permission needed"),
              detail: t(
                "qr.cameraDeniedDetail",
                "To scan a QR card, allow camera access for this site in your browser settings, then tap Start Scanning again."
              ),
            }
          : {
              title: t("qr.cameraUnavailable", "Camera unavailable"),
              detail:
                e?.message ||
                t("qr.cameraFallback", "We couldn't open the camera. You can still find the record by typing the ID below."),
            }
      );
    }
  };

  const handleDecode = async (decoded) => {
    if (!decoded) return;
    stopCamera();
    setPhase("decoding");
    await resolveId(extractId(String(decoded)));
  };

  // Accepts a raw QR payload or a manually typed full ID.
  const extractId = (raw) => {
    const tokens = String(raw).trim().split(/[\s:]+/);
    return tokens[tokens.length - 1] || "";
  };

  const resolveId = async (id) => {
    if (!id) {
      setPhase("invalid");
      return;
    }
    setPhase("decoding");
    setBen(null);
    setHousehold(null);
    try {
      if (isHouseholdId(id)) {
        // Household QRs first — fall back to beneficiary resolve below.
        try {
          const d = await api.get(`/households/resolve/${encodeURIComponent(id)}`);
          setHousehold({
            ...(d.household || {}),
            visits: d.visits || [],
            members: d.members || [],
            followups: d.followups || [],
          });
          setPhase("found");
          return;
        } catch {}
      }
      const d = await api.get(`/beneficiaries/resolve/${encodeURIComponent(id)}`);
      setBen({
        ...(d.beneficiary || {}),
        visits: d.visits || [],
        followups: d.followups || [],
        alerts: d.alerts || [],
      });
      setPhase("found");
    } catch (e) {
      setPhase("invalid");
    }
  };

  const nextFollowup = () => {
    const fu = (ben?.followups || []).find((f) => f.status !== "completed" && f.status !== "done");
    return fu?.due_date || ben?.next_followup_date || null;
  };

  const reset = () => {
    setBen(null);
    setHousehold(null);
    setPhase("idle");
    setManualId("");
    setCamError(null);
  };

  /* --------------------------- QR generator (demo) --------------------------- */
  const loadGenerator = async () => {
    setGenLoading(true);
    try {
      const [benList, hhList] = await Promise.all([
        api.get("/beneficiaries").catch(() => ({ beneficiaries: [] })),
        api.get("/households").catch(() => ({ households: [] })),
      ]);
      const firstBen = (benList.beneficiaries || [])[0] || null;
      const firstHh = (hhList.households || [])[0] || null;
      if (firstBen) {
        try {
          const qr = await api.get(`/beneficiaries/${firstBen.id}/qr`);
          setGenBen({ ...firstBen, data_url: qr.data_url });
        } catch {
          setGenBen(firstBen);
        }
      }
      if (firstHh) {
        try {
          const qr = await api.get(`/households/${firstHh.id}/qr`);
          setGenHh({ ...firstHh, data_url: qr.data_url });
        } catch {
          setGenHh(firstHh);
        }
      }
      if (!firstBen && !firstHh) showToast(t("qr.notFound"), "warn");
    } catch (e) {
      showToast(e.message || t("err.generic"), "error");
    } finally {
      setGenLoading(false);
    }
  };

  const downloadJson = (payload, name) => {
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${name}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      {/* header */}
      <motion.div
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: "easeOut" }}
        className="text-center"
      >
        <h2 className="text-xl font-extrabold text-teal-deep sm:text-2xl">{t("qr.connectTitle", "Connect with Your Beneficiary")}</h2>
        <p className="mx-auto mt-1.5 max-w-md text-sm font-medium leading-relaxed text-teal-deep/55">
          {t(
            "qr.connectSub",
            "Scan the QR printed on a beneficiary's health card or a household card to open the record and start a voice visit."
          )}
        </p>
      </motion.div>

      {/* scanner card */}
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.08, ease: "easeOut" }}
        className="card-ivory overflow-hidden"
      >
        <div className="relative aspect-[4/3] w-full bg-gradient-to-br from-teal-deep to-midnight">
          <video
            ref={videoRef}
            playsInline
            muted
            className={`absolute inset-0 h-full w-full object-cover ${cameraOn ? "opacity-100" : "opacity-0"}`}
          />

          {/* scanning frame overlay */}
          {cameraOn && phase === "scanning" && (
            <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
              <div className="relative h-56 w-56 max-w-[70%]">
                {[
                  "left-0 top-0 border-l-4 border-t-4 rounded-tl-2xl",
                  "right-0 top-0 border-r-4 border-t-4 rounded-tr-2xl",
                  "left-0 bottom-0 border-l-4 border-b-4 rounded-bl-2xl",
                  "right-0 bottom-0 border-r-4 border-b-4 rounded-br-2xl",
                ].map((pos) => (
                  <span key={pos} className={`absolute h-10 w-10 border-mint ${pos}`} />
                ))}
                <motion.div
                  animate={{ top: ["6%", "92%", "6%"] }}
                  transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut" }}
                  className="absolute inset-x-3 h-0.5 rounded-full bg-mint shadow-[0_0_14px_rgba(240,120,173,0.9)]"
                />
              </div>
            </div>
          )}

          {/* success checkmark pop */}
          <AnimatePresence>
            {phase === "decoding" && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="absolute inset-0 flex items-center justify-center bg-teal-deep/60 backdrop-blur-sm"
              >
                <motion.div
                  initial={{ scale: 0.4, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  transition={{ type: "spring", damping: 13 }}
                >
                  <CheckCircle2 size={56} className="text-mint" strokeWidth={2.4} />
                </motion.div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* idle / error cover */}
          {!cameraOn && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 px-6 text-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-mint/15">
                <ScanLine size={30} className="text-mint" strokeWidth={1.8} />
              </div>
              {camError ? (
                <>
                  <p className="text-sm font-extrabold text-white">{camError.title}</p>
                  <p className="max-w-xs text-xs font-medium leading-relaxed text-white/60">{camError.detail}</p>
                </>
              ) : (
                <p className="max-w-xs text-xs font-medium leading-relaxed text-white/60">
                  {t("qr.scanHint", "Tap \"Start Scanning\" and hold the card steady inside the frame.")}
                </p>
              )}
            </div>
          )}
        </div>

        <div className="flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs font-semibold text-teal-deep/50">
            {cameraOn ? t("qr.cameraScanning", "Camera is scanning… hold the card steady.") : t("qr.cameraOff", "Camera is off.")}
          </p>
          <div className="flex gap-2.5">
            {cameraOn ? (
              <button
                onClick={() => {
                  stopCamera();
                  setPhase("idle");
                }}
                className="flex items-center gap-2 rounded-full bg-teal-deep/5 px-5 py-2.5 text-sm font-bold text-teal-deep/70 transition-colors hover:bg-coral/10 hover:text-coral"
              >
                <CameraOff size={16} strokeWidth={2.2} /> {t("qr.stopCamera", "Stop Camera")}
              </button>
            ) : (
              <button
                onClick={startCamera}
                disabled={!hasCamera}
                className="btn-mint flex items-center gap-2 px-5 py-2.5 text-sm disabled:opacity-50"
              >
                <Camera size={16} strokeWidth={2.4} />
                {camError ? t("qr.tryAgain", "Try Again") : t("qr.startScan", "Start Scanning")}
              </button>
            )}
            {(phase === "invalid" || ben || household) && (
              <button
                onClick={reset}
                className="flex items-center gap-2 rounded-full bg-teal-deep/5 px-4 py-2.5 text-sm font-bold text-teal-deep/70 transition-colors hover:bg-teal-deep/10"
              >
                <RotateCcw size={15} strokeWidth={2.2} /> {t("common.cancel")}
              </button>
            )}
          </div>
        </div>
      </motion.div>

      {!hasCamera && (
        <div className="card-ivory p-4 text-center text-xs font-semibold text-teal-deep/55">
          {t("qr.noCamera", "No camera detected on this device — use the manual ID lookup below.")}
        </div>
      )}

      {/* invalid QR state */}
      {phase === "invalid" && (
        <div className="card-ivory border-coral/30 p-5">
          <div className="flex items-start gap-3.5">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-coral/15">
              <XCircle size={22} className="text-coral" strokeWidth={2.2} />
            </div>
            <div className="min-w-0">
              <p className="text-sm font-extrabold text-teal-deep">{t("qr.invalid")}</p>
              <p className="mt-1 text-xs font-medium text-teal-deep/55">
                {t("qr.invalidHint", "Check that you scanned an ASHA Swar Nirantar card, or register the record first.")}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* resolved household card */}
      <AnimatePresence>
        {phase === "found" && household && (
          <motion.div
            key="hh"
            initial={{ opacity: 0, y: 18, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ type: "spring", damping: 22, stiffness: 300 }}
            className="card-ivory p-5"
          >
            <div className="flex items-start gap-4">
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-teal-deep text-mint">
                <HomeIcon size={22} strokeWidth={2.2} />
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-lg font-extrabold text-teal-deep">{household.village}</p>
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  <span className="chip bg-mint/15 text-pink">{t("qr.household")}</span>
                  <span className="chip bg-teal-deep/5 font-mono text-[0.68rem] text-teal-deep/60">{household.qr_id}</span>
                  <span className="chip bg-teal-deep/5 text-teal-deep/55">
                    <Users size={11} /> {t("households.members")}: {(household.members || []).length}
                  </span>
                </div>
              </div>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-3">
              <div className="rounded-2xl bg-ivory/80 px-4 py-3">
                <p className="text-[0.65rem] font-extrabold uppercase tracking-wider text-teal-deep/45">{t("households.healthVisits")}</p>
                <p className="mt-0.5 text-xl font-extrabold text-teal-deep">{(household.visits || []).length}</p>
              </div>
              <div className="rounded-2xl bg-ivory/80 px-4 py-3">
                <p className="text-[0.65rem] font-extrabold uppercase tracking-wider text-teal-deep/45">{t("households.nextFollowup")}</p>
                <p className="mt-0.5 truncate text-sm font-extrabold text-teal-deep">
                  {(household.followups || []).find((f) => f.status !== "completed")?.due_date || "—"}
                </p>
              </div>
            </div>
            <button
              onClick={() => navigate(`/app/household-health?household=${household.id}`)}
              className="btn-mint mt-4 flex w-full items-center justify-center gap-2 px-4 py-3 text-sm"
            >
              <Mic size={16} strokeWidth={2.4} /> {t("households.startVoiceVisit")}
            </button>
            <button
              onClick={() => navigate(`/app/households/${household.id}`)}
              className="mt-2 flex w-full items-center justify-center gap-2 rounded-full bg-teal-deep/5 px-4 py-2.5 text-sm font-bold text-teal-deep/60 transition-colors hover:bg-teal-deep/10"
            >
              {t("households.timeline")}
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* resolved beneficiary card */}
      <AnimatePresence>
        {phase === "found" && ben && (
          <motion.div
            key="ben"
            initial={{ opacity: 0, y: 18, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ type: "spring", damping: 22, stiffness: 300 }}
            className="card-ivory p-5"
          >
            <div className="flex items-start gap-4">
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-teal-deep text-base font-extrabold text-mint">
                {initials(ben.name)}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-lg font-extrabold text-teal-deep">{ben.name}</p>
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  <span className="chip bg-mint/15 text-pink">{categoryLabel(ben.category, t)}</span>
                  <span className="chip bg-teal-deep/5 font-mono text-[0.68rem] text-teal-deep/60">{ben.qr_id}</span>
                  {ben.village && (
                    <span className="chip bg-teal-deep/5 text-teal-deep/55">
                      <QrCode size={11} /> {ben.village}
                    </span>
                  )}
                </div>
              </div>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-3">
              <div className="rounded-2xl bg-ivory/80 px-4 py-3">
                <p className="text-[0.65rem] font-extrabold uppercase tracking-wider text-teal-deep/45">{t("qr.prevVisits", "Previous visits")}</p>
                <p className="mt-0.5 text-xl font-extrabold text-teal-deep">{(ben.visits || []).length}</p>
              </div>
              <div className="rounded-2xl bg-ivory/80 px-4 py-3">
                <p className="text-[0.65rem] font-extrabold uppercase tracking-wider text-teal-deep/45">{t("qr.nextAppt", "Next appointment")}</p>
                <p className="mt-0.5 truncate text-sm font-extrabold text-teal-deep">{nextFollowup() || "—"}</p>
              </div>
            </div>
            <button
              onClick={() => navigate(`/app/voice-visit?beneficiary=${ben.id}`)}
              className="btn-mint mt-4 flex w-full items-center justify-center gap-2 px-4 py-3 text-sm"
            >
              <Mic size={16} strokeWidth={2.4} /> {t("households.startVoiceVisit")}
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* manual fallback */}
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.16, ease: "easeOut" }}
        className="card-ivory p-5"
      >
        <p className="text-sm font-extrabold text-teal-deep">{t("qr.manualTitle", "Can't scan? Find by ID")}</p>
        <p className="mt-0.5 text-xs font-medium text-teal-deep/50">
          {t("qr.manualHint", "Type the full ID printed on the card (beneficiary ASN-… or household HN-…).")}
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            resolveId(extractId(manualId));
          }}
          className="mt-3 flex gap-2.5"
        >
          <input
            value={manualId}
            onChange={(e) => setManualId(e.target.value)}
            placeholder="ASN-0000-0000 / HN-4KDP-7RWM"
            className={INPUT}
          />
          <button type="submit" className="shrink-0 rounded-full bg-teal-deep px-5 py-2.5 text-sm font-bold text-mint transition-transform hover:-translate-y-0.5">
            {t("qr.findById", "Find by ID")}
          </button>
        </form>
      </motion.div>

      {/* QR generator (demo) */}
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.2, ease: "easeOut" }}
        className="card-ivory p-5"
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-extrabold text-teal-deep">{t("qr.generator")}</p>
            <p className="mt-0.5 text-xs font-medium text-teal-deep/50">
              {t("qr.generatorHint", "Generate printable QR cards for a demo beneficiary and household — PNG + matching JSON.")}
            </p>
          </div>
          <button
            onClick={loadGenerator}
            disabled={genLoading}
            className="btn-mint flex shrink-0 items-center gap-2 px-4 py-2.5 text-sm disabled:opacity-60"
          >
            <QrCode size={15} strokeWidth={2.4} />
            {genLoading ? t("common.loading") : t("qr.generate", "Generate")}
          </button>
        </div>

        {(genBen || genHh) && (
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            {genBen && (
              <div className="rounded-3xl bg-ivory/80 p-4 text-center">
                <p className="mb-1 text-[0.65rem] font-extrabold uppercase tracking-wider text-teal-deep/45">{t("qr.beneficiary")}</p>
                {genBen.data_url ? (
                  <img src={genBen.data_url} alt={`QR ${genBen.qr_id}`} className="mx-auto h-36 w-36 rounded-2xl border border-teal-deep/10 bg-white p-1.5" />
                ) : (
                  <div className="mx-auto flex h-36 w-36 items-center justify-center rounded-2xl bg-mint-soft text-teal-deep">
                    <QrCode size={40} />
                  </div>
                )}
                <p className="mt-2 truncate text-sm font-extrabold text-teal-deep">{genBen.name}</p>
                <p className="font-mono text-[0.68rem] font-bold tracking-wider text-teal-deep/55">{genBen.qr_id}</p>
                <div className="mt-3 flex flex-col gap-2">
                  {genBen.data_url && (
                    <a href={genBen.data_url} download={`${genBen.qr_id}.png`} className="btn-mint flex items-center justify-center gap-2 px-3 py-2 text-xs">
                      <Download size={13} /> {t("common.downloadPng")}
                    </a>
                  )}
                  <button
                    onClick={() => downloadJson({ type: "beneficiary", qr_id: genBen.qr_id, name: genBen.name, category: genBen.category, village: genBen.village }, `${genBen.qr_id}`)}
                    className="flex items-center justify-center gap-2 rounded-full bg-teal-deep/5 px-3 py-2 text-xs font-bold text-teal-deep/60 transition-colors hover:bg-teal-deep/10"
                  >
                    <FileJson size={13} /> {t("common.downloadJson")}
                  </button>
                </div>
              </div>
            )}
            {genHh && (
              <div className="rounded-3xl bg-ivory/80 p-4 text-center">
                <p className="mb-1 text-[0.65rem] font-extrabold uppercase tracking-wider text-teal-deep/45">{t("qr.household")}</p>
                {genHh.data_url ? (
                  <img src={genHh.data_url} alt={`QR ${genHh.qr_id}`} className="mx-auto h-36 w-36 rounded-2xl border border-teal-deep/10 bg-white p-1.5" />
                ) : (
                  <div className="mx-auto flex h-36 w-36 items-center justify-center rounded-2xl bg-mint-soft text-teal-deep">
                    <HomeIcon size={40} />
                  </div>
                )}
                <p className="mt-2 truncate text-sm font-extrabold text-teal-deep">{genHh.village}</p>
                <p className="font-mono text-[0.68rem] font-bold tracking-wider text-teal-deep/55">{genHh.qr_id}</p>
                <div className="mt-3 flex flex-col gap-2">
                  {genHh.data_url && (
                    <a href={genHh.data_url} download={`${genHh.qr_id}.png`} className="btn-mint flex items-center justify-center gap-2 px-3 py-2 text-xs">
                      <Download size={13} /> {t("common.downloadPng")}
                    </a>
                  )}
                  <button
                    onClick={() => downloadJson({ type: "household", qr_id: genHh.qr_id, village: genHh.village, member_count: genHh.member_count }, `${genHh.qr_id}`)}
                    className="flex items-center justify-center gap-2 rounded-full bg-teal-deep/5 px-3 py-2 text-xs font-bold text-teal-deep/60 transition-colors hover:bg-teal-deep/10"
                  >
                    <FileJson size={13} /> {t("common.downloadJson")}
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </motion.div>

      {/* instructions + security note */}
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.22, ease: "easeOut" }}
        className="card-ivory space-y-3 p-5"
      >
        <p className="text-sm font-extrabold text-teal-deep">{t("qr.tips", "Scanning tips")}</p>
        {[
          { icon: Hand, text: t("qr.tipHold", "Hold the card steady about 15–20 cm from the camera.") },
          { icon: Lightbulb, text: t("qr.tipLight", "Use good lighting — avoid glare and deep shadows.") },
          { icon: CreditCard, text: t("qr.tipCard", "The QR is printed on the beneficiary or household card.") },
        ].map(({ icon: Icon, text }) => (
          <div key={text} className="flex items-center gap-3">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-mint-soft">
              <Icon size={14} className="text-teal-deep" strokeWidth={2.2} />
            </div>
            <p className="text-xs font-semibold text-teal-deep/65">{text}</p>
          </div>
        ))}
        <div className="mt-1 flex items-start gap-2.5 rounded-2xl bg-mint-soft/60 px-3.5 py-3">
          <ShieldCheck size={16} className="mt-0.5 shrink-0 text-teal-deep" strokeWidth={2.2} />
          <p className="text-xs font-semibold leading-relaxed text-teal-deep/70">
            {t("qr.security", "The QR contains only an anonymous ID — never health data. Records require your authenticated login.")}
          </p>
        </div>
      </motion.div>
    </div>
  );
}
