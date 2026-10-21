import React, { type ReactNode } from "react";
import { Tooltip } from "@/components/ui/Tooltip";

export function Panel({
  title,
  tooltip,
  subtitle,
  className = "",
  children,
}: {
  title: string;
  tooltip: string;
  subtitle?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section className={`min-w-0 space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm ${className}`.trim()}>
      <div>
        <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-800">
          <span>{title}</span>
          <Tooltip label={title} content={tooltip} />
        </h3>
        {subtitle && (
          <p className="mt-0.5 truncate text-xs text-slate-500" title={subtitle}>
            {subtitle}
          </p>
        )}
      </div>
      {children}
    </section>
  );
}
