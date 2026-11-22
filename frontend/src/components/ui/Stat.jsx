import React from "react";
import { motion } from "framer-motion";

const TONES = {
  mint: { icon: "bg-mint/15 text-pink", glow: "shadow-[0_4px_20px_rgba(240,120,173,0.18)]" },
  teal: { icon: "bg-teal-deep text-pink", glow: "shadow-[0_4px_20px_rgba(16,12,24,0.22)]" },
  lavender: { icon: "bg-lavender/20 text-midnight", glow: "shadow-[0_4px_20px_rgba(183,163,255,0.25)]" },
  coral: { icon: "bg-coral/15 text-coral", glow: "shadow-[0_4px_20px_rgba(255,128,111,0.25)]" },
};

/**
 * Stat card.
 * <Stat label="Total Beneficiaries" value={128} icon={Users} tone="mint" delay={0} />
 */
export default function Stat({ label, value, icon: Icon, tone = "mint", sub, delay = 0 }) {
  const t = TONES[tone] || TONES.mint;
  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay, ease: "easeOut" }}
      className="card-ivory flex min-w-0 items-center gap-3.5 p-4 sm:p-5"
    >
      <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl ${t.icon} ${t.glow}`}>
        {Icon && <Icon size={20} strokeWidth={2} />}
      </div>
      <div className="min-w-0">
        <p className="text-[0.68rem] font-bold uppercase tracking-wider text-teal-deep/50 leading-snug break-words">{label}</p>
        <p className="mt-0.5 text-2xl font-extrabold leading-none text-teal-deep">{value ?? "—"}</p>
        {sub && <p className="mt-1 text-[0.7rem] font-medium text-teal-deep/45 leading-snug break-words">{sub}</p>}
      </div>
    </motion.div>
  );
}
