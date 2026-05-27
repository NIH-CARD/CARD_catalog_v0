import { NavLink } from "react-router-dom";

const NAV = [
  { to: "/", label: "Home", end: true },
  { to: "/resources", label: "Resources" },
  { to: "/publications", label: "Publications" },
  { to: "/code", label: "Code" },
  { to: "/datasets", label: "Datasets" },
  { to: "/cellular-models", label: "Cellular Models" },
  { to: "/about", label: "About" },
];

interface Props {
  query: string;
  onQueryChange: (q: string) => void;
}

export function Header({ query, onQueryChange }: Props) {
  return (
    <header className="bg-accent text-white px-6 py-3 flex items-center gap-6 shadow">
      <NavLink to="/" className="font-semibold text-lg tracking-tight">
        CARD Catalog
      </NavLink>
      <nav className="flex gap-4 text-sm">
        {NAV.map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            end={n.end}
            className={({ isActive }) =>
              isActive
                ? "text-white border-b border-white pb-px"
                : "text-white/80 hover:text-white"
            }
          >
            {n.label}
          </NavLink>
        ))}
      </nav>
      <div className="flex-1" />
      <input
        value={query}
        onChange={(e) => onQueryChange(e.target.value)}
        placeholder="Search title, abstract, authors…"
        className="w-72 px-3 py-1.5 rounded text-sm text-slate-800 placeholder-slate-400 bg-white/95 focus:outline-none focus:ring-2 focus:ring-white"
      />
    </header>
  );
}
