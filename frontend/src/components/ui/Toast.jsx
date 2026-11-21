import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { AnimatePresence, motion } from "framer-motion";
import { Info, CheckCircle2, AlertTriangle, XCircle, X } from "lucide-react";

/* ---------------------------------------------------------------------------
   Self-contained toast system. Pages just call `showToast(msg, type)` —
   the host container mounts itself on first use, zero App.jsx wiring.
--------------------------------------------------------------------------- */

const listeners = new Set();
let stack = [];
let counter = 0;
let hostMounted = false;
const recentToasts = new Map(); // `${type}:${message}` -> timestamp

function emit() {
  listeners.forEach((l) => l(stack));
}

export function dismissToast(id) {
  stack = stack.filter((t) => t.id !== id);
  emit();
}

export function showToast(message, type = "info") {
  if (!message) return;
  const key = `${type}:${message}`;
  const now = Date.now();
  const last = recentToasts.get(key) || 0;
  if (now - last < 2000) return null;
  recentToasts.set(key, now);
  // Prune old entries occasionally
  if (recentToasts.size > 50) {
    for (const [k, ts] of recentToasts) if (now - ts > 5000) recentToasts.delete(k);
  }
  const id = ++counter;
  stack = [...stack, { id, message, type }];
  ensureHost();
  emit();
  setTimeout(() => dismissToast(id), 3500);
  return id;
}

function ensureHost() {
  if (hostMounted || typeof document === "undefined") return;
  hostMounted = true;
  const el = document.createElement("div");
  el.id = "asn-toast-host";
  document.body.appendChild(el);
  createRoot(el).render(<ToastViewport />);
}

const TYPE_META = {
  info: { Icon: Info, color: "text-mint" },
  success: { Icon: CheckCircle2, color: "text-mint" },
  warn: { Icon: AlertTriangle, color: "text-coral" },
  error: { Icon: XCircle, color: "text-coral" },
};

function ToastViewport() {
  const [items, setItems] = useState([]);
  useEffect(() => {
    const l = (s) => setItems([...s]);
    listeners.add(l);
    return () => listeners.delete(l);
  }, []);

  return (
    <div
      aria-live="polite"
      className="pointer-events-none fixed inset-x-0 bottom-4 z-[999] flex flex-col items-center gap-2.5 px-4 sm:inset-x-auto sm:bottom-auto sm:right-4 sm:top-4 sm:items-end sm:px-0"
    >
      <AnimatePresence>
        {items.map((t) => {
          const { Icon, color } = TYPE_META[t.type] || TYPE_META.info;
          return (
            <motion.div
              key={t.id}
              layout
              initial={{ opacity: 0, y: 18, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 10, scale: 0.95 }}
              transition={{ duration: 0.22, ease: "easeOut" }}
              className="pointer-events-auto flex w-full max-w-sm items-start gap-2.5 rounded-2xl bg-teal-deep px-4 py-3 text-white shadow-glass sm:w-auto"
            >
              <Icon size={18} className={`mt-0.5 shrink-0 ${color}`} />
              <p className="min-w-0 flex-1 text-sm font-medium leading-snug break-words">{t.message}</p>
              <button
                onClick={() => dismissToast(t.id)}
                aria-label="Dismiss notification"
                className="mt-0.5 shrink-0 rounded-full p-0.5 text-white/50 transition-colors hover:text-white"
              >
                <X size={14} />
              </button>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
