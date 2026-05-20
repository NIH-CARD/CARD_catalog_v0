import { useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

interface Props {
  children: ReactNode;
  /** What to render inside the popover. Can be JSX, plain text, or a function. */
  content: ReactNode | (() => ReactNode);
  /** Pixels of horizontal nudge for the popover. */
  offsetX?: number;
  /** Pixels of vertical nudge for the popover (below the anchor). */
  offsetY?: number;
}

/**
 * Hover-revealed popover. Portals into <body> so it isn't clipped by the
 * scrollable table containers. Positioned right under the hovered element.
 */
export function HoverInfo({ children, content, offsetX = 0, offsetY = 4 }: Props) {
  const ref = useRef<HTMLSpanElement>(null);
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number }>({ top: 0, left: 0 });

  const handleEnter = () => {
    if (!ref.current) return;
    const r = ref.current.getBoundingClientRect();
    setPos({ top: r.bottom + offsetY, left: r.left + offsetX });
    setOpen(true);
  };
  const handleLeave = () => setOpen(false);

  return (
    <span
      ref={ref}
      onMouseEnter={handleEnter}
      onMouseLeave={handleLeave}
      className="inline-block"
    >
      {children}
      {open &&
        createPortal(
          <div
            className="fixed z-50 max-w-md bg-white border border-slate-200 shadow-lg rounded p-3 text-xs text-slate-700 pointer-events-none"
            style={{ top: pos.top, left: pos.left }}
          >
            {typeof content === "function" ? content() : content}
          </div>,
          document.body,
        )}
    </span>
  );
}

/**
 * Convenience renderer for a list of key/value pairs inside HoverInfo content.
 * Empty values are skipped.
 */
export function InfoList({ rows }: { rows: { label: string; value: ReactNode }[] }) {
  return (
    <dl className="grid grid-cols-[max-content,1fr] gap-x-3 gap-y-1">
      {rows
        .filter((r) => r.value !== "" && r.value !== null && r.value !== undefined)
        .map((r) => (
          <span key={r.label} className="contents">
            <dt className="text-slate-500 uppercase tracking-wide text-[10px] font-semibold pt-0.5">
              {r.label}
            </dt>
            <dd className="text-slate-700">{r.value}</dd>
          </span>
        ))}
    </dl>
  );
}
