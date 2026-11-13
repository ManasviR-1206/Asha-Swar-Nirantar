import React from "react";

const WIDTHS = ["w-full", "w-11/12", "w-full", "w-5/6", "w-full", "w-3/4"];

/**
 * Shimmer loading placeholder.
 * <Skeleton lines={4} />          — stacked text-like bars
 * <Skeleton lines={3} className="p-5" /> — custom wrapper
 */
export default function Skeleton({ lines = 3, className = "" }) {
  return (
    <div className={`space-y-3 ${className}`} aria-busy="true" role="status">
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className={`skeleton h-4 ${WIDTHS[i % WIDTHS.length]}`}
          style={{ opacity: 1 - i * 0.12 }}
        />
      ))}
    </div>
  );
}

/** Block-level skeleton for cards / rows. */
export function SkeletonCard({ className = "" }) {
  return (
    <div className={`card-ivory p-5 ${className}`}>
      <div className="flex items-center gap-3">
        <div className="skeleton h-11 w-11 shrink-0 rounded-2xl" />
        <div className="min-w-0 flex-1 space-y-2">
          <div className="skeleton h-3.5 w-1/2" />
          <div className="skeleton h-3 w-1/3" />
        </div>
      </div>
      <div className="mt-4">
        <Skeleton lines={2} />
      </div>
    </div>
  );
}
