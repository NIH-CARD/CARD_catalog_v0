import type { ReactNode } from "react";
import { Header } from "./Header";

interface Props {
  query: string;
  onQueryChange: (q: string) => void;
  rail: ReactNode;
  title: string;
  count?: string;
  children: ReactNode;
}

export function PageShell({
  query,
  onQueryChange,
  rail,
  title,
  count,
  children,
}: Props) {
  return (
    <div className="min-h-screen flex flex-col">
      <Header query={query} onQueryChange={onQueryChange} />
      <div className="flex flex-1">
        {rail}
        <main className="flex-1 px-6 py-4 overflow-hidden">
          <div className="flex items-baseline justify-between mb-3">
            <h1 className="text-xl font-semibold text-slate-800">{title}</h1>
            {count && <div className="text-sm text-slate-600">{count}</div>}
          </div>
          {children}
        </main>
      </div>
    </div>
  );
}
