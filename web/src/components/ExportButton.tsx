import { useEffect, useRef, useState } from "react";
import { exportRows } from "../lib/export";

const FORMATS = ["csv", "tsv", "xlsx", "json"] as const;

interface Props {
  rows: object[];
  filename: string;
}

export function ExportButton({ rows, filename }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  return (
    <div ref={ref} className="relative inline-block">
      <button
        onClick={() => setOpen((v) => !v)}
        disabled={rows.length === 0}
        className="inline-flex items-center gap-1 px-3 py-1.5 rounded border border-slate-200 bg-white text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
      >
        <span>↓</span>
        <span>Export ({rows.length.toLocaleString()})</span>
      </button>
      {open && (
        <div className="absolute right-0 z-20 mt-1 w-28 rounded border border-slate-200 bg-white shadow-md py-1">
          {FORMATS.map((fmt) => (
            <button
              key={fmt}
              onClick={() => {
                setOpen(false);
                exportRows(rows, filename, fmt);
              }}
              className="w-full px-3 py-1.5 text-left text-sm text-slate-700 hover:bg-slate-50 font-mono"
            >
              .{fmt.toUpperCase()}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
