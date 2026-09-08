import { useState, type ReactNode } from "react";
import { Chips } from "./Chips";

interface FieldProps {
  label: string;
  value: string | undefined | null;
  /** Render as chips (semicolon-delimited by default) */
  chips?: boolean;
  delimiter?: string;
  /** Truncate long text and show a toggle */
  expandable?: boolean;
  /** Max chars before truncation kicks in */
  maxChars?: number;
  /** Render value as a link */
  href?: string;
}

export function Field({
  label,
  value,
  chips,
  delimiter = ";",
  expandable,
  maxChars = 280,
  href,
}: FieldProps) {
  const [expanded, setExpanded] = useState(false);
  if (!value) return null;

  let content: ReactNode;

  if (chips) {
    content = <Chips value={value} delimiter={delimiter} />;
  } else if (expandable && value.length > maxChars && !expanded) {
    content = (
      <span className="text-xs text-slate-700">
        {value.slice(0, maxChars)}…{" "}
        <button
          className="text-accent underline hover:no-underline"
          onClick={() => setExpanded(true)}
        >
          more
        </button>
      </span>
    );
  } else if (expandable && value.length > maxChars && expanded) {
    content = (
      <span className="text-xs text-slate-700">
        {value}{" "}
        <button
          className="text-accent underline hover:no-underline"
          onClick={() => setExpanded(false)}
        >
          less
        </button>
      </span>
    );
  } else if (href) {
    content = (
      <a
        href={href}
        target="_blank"
        rel="noreferrer"
        className="text-xs text-accent hover:underline break-all"
      >
        {value}
      </a>
    );
  } else {
    content = <span className="text-xs text-slate-700">{value}</span>;
  }

  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
        {label}
      </span>
      {content}
    </div>
  );
}

interface SectionProps {
  title: string;
  children: ReactNode;
  defaultOpen?: boolean;
}

export function Section({ title, children, defaultOpen = false }: SectionProps) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-t border-slate-100 pt-2 mt-2">
      <button
        className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500 hover:text-slate-700 w-full text-left"
        onClick={() => setOpen((v) => !v)}
      >
        <span>{open ? "▾" : "▸"}</span>
        {title}
      </button>
      {open && <div className="mt-2 flex flex-col gap-2">{children}</div>}
    </div>
  );
}

interface CardProps {
  title: ReactNode;
  subtitle?: ReactNode;
  badge?: ReactNode;
  children: ReactNode;
}

export function BrowseCard({ title, subtitle, badge, children }: CardProps) {
  return (
    <div className="bg-white border border-slate-200 rounded-lg p-4 flex flex-col gap-2 hover:shadow-sm transition-shadow">
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-col gap-0.5 min-w-0">
          <div className="text-sm font-semibold text-slate-800 leading-snug">{title}</div>
          {subtitle && (
            <div className="text-xs text-slate-500">{subtitle}</div>
          )}
        </div>
        {badge && <div className="shrink-0">{badge}</div>}
      </div>
      <div className="flex flex-col gap-2">{children}</div>
    </div>
  );
}

interface BrowseGridProps {
  children: ReactNode;
}

export function BrowseGrid({ children }: BrowseGridProps) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3 pb-4">
      {children}
    </div>
  );
}
