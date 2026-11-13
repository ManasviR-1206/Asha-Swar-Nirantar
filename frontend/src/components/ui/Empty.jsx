import React from "react";
import { motion } from "framer-motion";
import { HeartHandshake } from "lucide-react";

/**
 * Elegant empty state.
 * <Empty icon={X} title="..." subtitle="..." action={<button/>} />
 */
export default function Empty({
  icon: Icon = HeartHandshake,
  title,
  subtitle,
  action,
  className = "",
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: "easeOut" }}
      className={`flex flex-col items-center justify-center px-6 py-12 text-center ${className}`}
    >
      <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-mint-soft">
        <Icon size={28} className="text-teal-deep" strokeWidth={1.8} />
      </div>
      <h3 className="text-base font-bold text-teal-deep">{title}</h3>
      {subtitle && <p className="mt-1.5 max-w-xs text-sm leading-relaxed text-teal-deep/55">{subtitle}</p>}
      {action && <div className="mt-5">{action}</div>}
    </motion.div>
  );
}
