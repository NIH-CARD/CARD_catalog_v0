import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import type { Plugin } from "vite";
import type { IncomingMessage, ServerResponse } from "http";

function netlifyFunctionsPlugin(): Plugin {
  return {
    name: "netlify-functions",
    configureServer(server) {
      server.middlewares.use(
        (req: IncomingMessage, res: ServerResponse, next: () => void) => {
          if (req.url !== "/.netlify/functions/analyze") { next(); return; }

          const chunks: Buffer[] = [];
          req.on("data", (chunk: Buffer) => chunks.push(chunk));
          req.on("end", () => {
            const body = Buffer.concat(chunks);

            import("./netlify/functions/analyze.mjs")
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              .then(({ default: fn }: { default: (r: Request) => Promise<Response> }) => {
                const webReq = new Request(
                  "http://localhost/.netlify/functions/analyze",
                  {
                    method: req.method,
                    headers: Object.fromEntries(
                      Object.entries(req.headers as Record<string, string>).filter(
                        ([k]) => k !== "host",
                      ),
                    ),
                    body: body.length ? body : undefined,
                  },
                );
                return fn(webReq);
              })
              .then((webRes: Response) => {
                const outHeaders: Record<string, string> = {};
                webRes.headers.forEach((v: string, k: string) => { outHeaders[k] = v; });
                outHeaders["access-control-allow-origin"] = "*";
                res.writeHead(webRes.status, outHeaders);
                if (!webRes.body) { res.end(); return; }
                const reader = webRes.body.getReader();
                const pump = (): void => {
                  reader.read().then(({ done, value }) => {
                    if (done) { res.end(); return; }
                    res.write(value);
                    pump();
                  });
                };
                pump();
              })
              .catch((err: unknown) => {
                console.error("[analyze] handler error:", err);
                res.writeHead(500, { "Content-Type": "application/json" });
                res.end(JSON.stringify({ error: String(err) }));
              });
          });
        },
      );
    },
  };
}

export default defineConfig({
  plugins: [react(), netlifyFunctionsPlugin()],
  base: "/",
  server: { port: 5173 },
});
