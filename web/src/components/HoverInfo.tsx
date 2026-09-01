import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

interface Props {
  children: ReactNode;
  /** What to render inside the popover. Can be JSX, plain text, or a function. */
  content: ReactNode | (() => ReactNode);
  /** Pixels of horizontal nudge for the popover. */
  offsetX?: number;
  /** Pixels of vertical nudge for the popover (below the anchor). */
  offsetY?: number;
  /** When true, clicking the trigger pins the popover open - it survives the
   * mouse leaving, until a click anywhere outside it (trigger or popover).
   * Defaults to false, preserving pure-hover behavior for existing callers. */
  pinnable?: boolean;
}

/**
 * Hover-revealed popover. Portals into <body> so it isn't clipped by the
 * scrollable table containers. Positioned right under the hovered element.
 */
export function HoverInfo({ children, content, offsetX = 0, offsetY = 4, pinnable = false }: Props) {
  const ref = useRef<HTMLSpanElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number }>({ top: 0, left: 0 });

  const reveal = () => {
    if (!ref.current) return;
    const r = ref.current.getBoundingClientRect();
    setPos({ top: r.bottom + offsetY, left: r.left + offsetX });
    setOpen(true);
  };
  const handleEnter = () => {
    if (!pinned) reveal();
  };
  const handleLeave = () => {
    if (!pinned) setOpen(false);
  };
  const handleClick = () => {
    if (!pinnable) return;
    if (pinned) {
      setPinned(false);
      setOpen(false);
      return;
    }
    reveal();
    setPinned(true);
  };

  useEffect(() => {
    if (!pinned) return;
    const onOutsideClick = (e: MouseEvent) => {
      const target = e.target as Node;
      if (ref.current?.contains(target) || popoverRef.current?.contains(target)) return;
      setPinned(false);
      setOpen(false);
    };
    // Capture phase so this fires even if something in between (e.g. ReactFlow's
    // own pane/node handlers) calls stopPropagation() during the bubble phase.
    document.addEventListener("mousedown", onOutsideClick, true);
    return () => document.removeEventListener("mousedown", onOutsideClick, true);
  }, [pinned]);

  return (
    <span
      ref={ref}
      onMouseEnter={handleEnter}
      onMouseLeave={handleLeave}
      onClick={handleClick}
      className="inline-block"
    >
      {children}
      {open &&
        createPortal(
          <div
            ref={popoverRef}
            className={
              "fixed z-50 max-w-md bg-white border border-slate-200 shadow-lg rounded p-3 text-xs text-slate-700 " +
              (pinned ? "pointer-events-auto" : "pointer-events-none")
            }
            style={{ top: pos.top, left: pos.left }}
          >
            {pinned && (
              <button
                className="float-right text-slate-400 hover:text-slate-700 text-xs leading-none ml-2 -mt-0.5"
                onClick={(e) => {
                  e.stopPropagation();
                  setPinned(false);
                  setOpen(false);
                }}
                aria-label="Close"
              >
                ✕
              </button>
            )}
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
