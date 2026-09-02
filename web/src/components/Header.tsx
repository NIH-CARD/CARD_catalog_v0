import { NavLink } from "react-router-dom";

// Table pages (browse one table) vs. Connections (a cross-table tool, a
// different kind of page) vs. meta pages (about the catalog itself) - kept
// visually separate so the nav doesn't read as one flat list of same-weight items.
const TABLE_NAV = [
  { to: "/resources", label: "Resources" },
  { to: "/publications", label: "Publications" },
  { to: "/code", label: "Code" },
  { to: "/annotations", label: "Annotations" },
  { to: "/cellular-models", label: "Cellular Models" },
];

const CONNECTIONS_NAV = [{ to: "/connections", label: "Connections" }];

const SECONDARY_NAV = [
  { to: "/about", label: "About" },
  { to: "/docs", label: "Docs" },
];

interface Props {
  // Omit both on pages with no results list for the search box to filter
  // (currently just the home page) - render no search input there at all,
  // rather than one that silently discards everything typed into it.
  query?: string;
  onQueryChange?: (q: string) => void;
}

interface NavItem {
  to: string;
  label: string;
}

// "·" separates items within one group (same weight, closely related pages);
// "|" separates groups (Table pages vs. Connections vs. About/Docs) - two
// tiers of separator so the nav's grouping reads at a glance, not just from
// spacing/borders.
function NavGroup({ items, secondary = false }: { items: readonly NavItem[]; secondary?: boolean }) {
  return (
    <nav className="flex items-center gap-3 text-sm">
      {items.map((n, i) => (
        <span key={n.to} className="flex items-center gap-3">
          {i > 0 && <span className="text-white/30">·</span>}
          <NavLink
            to={n.to}
            className={({ isActive }) =>
              isActive
                ? "text-white border-b border-white pb-px"
                : secondary
                  ? "text-white/60 hover:text-white/90"
                  : "text-white/80 hover:text-white"
            }
          >
            {n.label}
          </NavLink>
        </span>
      ))}
    </nav>
  );
}

function GroupDivider() {
  return <span className="text-white/30 text-base select-none">|</span>;
}

export function Header({ query, onQueryChange }: Props) {
  return (
    <header className="bg-accent text-white py-3 flex items-center gap-6 shadow">
      {/* No horizontal padding on the header itself - this box starts at true
          x=0, same as FilterRail's `w-72` aside on table pages, so the divider
          at its right edge lands exactly where that sidebar's border does. */}
      <div className="w-72 shrink-0 flex items-center justify-between pl-6">
        <NavLink to="/" end className="font-semibold text-lg tracking-tight">
          CARD Catalog
        </NavLink>
        <GroupDivider />
      </div>
      <NavGroup items={TABLE_NAV} />
      <GroupDivider />
      <NavGroup items={CONNECTIONS_NAV} />
      <div className="flex-1" />
      <GroupDivider />
      <NavGroup items={SECONDARY_NAV} secondary />
      {onQueryChange && (
        <input
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          placeholder="Search title, abstract, authors…"
          className="w-72 mr-6 px-3 py-1.5 rounded text-sm text-slate-800 placeholder-slate-400 bg-white/95 focus:outline-none focus:ring-2 focus:ring-white"
        />
      )}
    </header>
  );
}
