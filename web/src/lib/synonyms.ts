import { useEffect, useMemo, useState } from "react";

interface SynonymGroup {
  canonical: string;
  synonyms: string[];
}

function buildLookup(groups: SynonymGroup[]): Map<string, string> {
  const lookup = new Map<string, string>();
  for (const g of groups) {
    for (const form of new Set([...g.synonyms, g.canonical])) {
      lookup.set(form.toLowerCase(), g.canonical);
    }
  }
  return lookup;
}

// One fetch per path, shared across every component that asks for it.
const cache = new Map<string, Promise<Map<string, string>>>();

function loadSynonymLookup(path: string): Promise<Map<string, string>> {
  let pending = cache.get(path);
  if (!pending) {
    pending = fetch(path)
      .then((res) => {
        if (!res.ok) throw new Error(`Failed to fetch ${path}: ${res.status}`);
        return res.json() as Promise<SynonymGroup[]>;
      })
      .then(buildLookup);
    cache.set(path, pending);
  }
  return pending;
}

/**
 * Returns a stable canonicalize(value) function, backed by a synonym-groups
 * JSON file (tables/{modality,disease}_synonyms.json, synced to public/data/).
 * Falls back to identity until the file loads and for any value with no match.
 */
export function useCanonicalizer(path: string): (value: string) => string {
  const [lookup, setLookup] = useState<Map<string, string> | null>(null);

  useEffect(() => {
    let active = true;
    loadSynonymLookup(path)
      .then((l) => active && setLookup(l))
      .catch(() => active && setLookup(new Map()));
    return () => {
      active = false;
    };
  }, [path]);

  return useMemo(() => {
    return (value: string) => lookup?.get(value.toLowerCase()) ?? value;
  }, [lookup]);
}

export const useModalityCanonicalizer = () => useCanonicalizer("/data/modality_synonyms.json");
export const useDiseaseCanonicalizer = () => useCanonicalizer("/data/disease_synonyms.json");
