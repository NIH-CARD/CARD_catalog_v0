import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

/**
 * URL-synced facet selection state.
 *
 * Each facet field is stored as one query param. Values inside a field are
 * pipe-separated so `|` never appears in real data. ?q=foo carries the text
 * search.
 */
export function useFacets<F extends string>(fields: readonly F[]) {
  const [searchParams, setSearchParams] = useSearchParams();

  const selections = useMemo(() => {
    const out = {} as Record<F, Set<string>>;
    for (const f of fields) {
      const raw = searchParams.get(f);
      out[f] = raw ? new Set(raw.split("|").filter(Boolean)) : new Set();
    }
    return out;
  }, [fields, searchParams]);

  const query = searchParams.get("q") ?? "";

  const setFacet = useCallback(
    (field: F, next: Set<string>) => {
      setSearchParams(
        (prev) => {
          const sp = new URLSearchParams(prev);
          if (next.size === 0) sp.delete(field);
          else sp.set(field, Array.from(next).join("|"));
          return sp;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const setQuery = useCallback(
    (q: string) => {
      setSearchParams(
        (prev) => {
          const sp = new URLSearchParams(prev);
          if (q) sp.set("q", q);
          else sp.delete("q");
          return sp;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const clearAll = useCallback(() => {
    setSearchParams(
      (prev) => {
        const sp = new URLSearchParams(prev);
        for (const f of fields) sp.delete(f);
        sp.delete("q");
        return sp;
      },
      { replace: true },
    );
  }, [fields, setSearchParams]);

  const totalSelected = useMemo(
    () => Object.values<Set<string>>(selections).reduce((n, s) => n + s.size, 0),
    [selections],
  );

  return { selections, query, setFacet, setQuery, clearAll, totalSelected };
}
