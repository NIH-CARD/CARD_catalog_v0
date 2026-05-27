import { useState } from "react";

export type AnalysisType = "resources" | "publications" | "code" | "cellular_models" | "pub_datasets";

export function useAnalysis() {
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const analyze = async (
    type: AnalysisType,
    rows: object[],
    filteredCount: number,
    totalCount: number,
  ) => {
    setLoading(true);
    setError(null);
    setText("");

    try {
      const response = await fetch("/.netlify/functions/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type, rows, filteredCount, totalCount }),
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({ error: response.statusText }));
        throw new Error(err.error ?? "Analysis failed");
      }

      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const payload = line.slice(6).trim();
          if (payload === "[DONE]") continue;
          try {
            const parsed = JSON.parse(payload);
            if (
              parsed.type === "content_block_delta" &&
              parsed.delta?.type === "text_delta"
            ) {
              setText((prev) => prev + parsed.delta.text);
            }
          } catch {
            // skip malformed SSE lines
          }
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Analysis failed");
    } finally {
      setLoading(false);
    }
  };

  return { text, loading, error, analyze };
}
