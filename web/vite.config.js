import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
function netlifyFunctionsPlugin() {
    return {
        name: "netlify-functions",
        configureServer: function (server) {
            server.middlewares.use(function (req, res, next) {
                if (req.url !== "/.netlify/functions/analyze") {
                    next();
                    return;
                }
                var chunks = [];
                req.on("data", function (chunk) { return chunks.push(chunk); });
                req.on("end", function () {
                    var body = Buffer.concat(chunks);
                    import("./netlify/functions/analyze.mjs")
                        // eslint-disable-next-line @typescript-eslint/no-explicit-any
                        .then(function (_a) {
                        var fn = _a.default;
                        var webReq = new Request("http://localhost/.netlify/functions/analyze", {
                            method: req.method,
                            headers: Object.fromEntries(Object.entries(req.headers).filter(function (_a) {
                                var k = _a[0];
                                return k !== "host";
                            })),
                            body: body.length ? body : undefined,
                        });
                        return fn(webReq);
                    })
                        .then(function (webRes) {
                        var outHeaders = {};
                        webRes.headers.forEach(function (v, k) { outHeaders[k] = v; });
                        outHeaders["access-control-allow-origin"] = "*";
                        res.writeHead(webRes.status, outHeaders);
                        if (!webRes.body) {
                            res.end();
                            return;
                        }
                        var reader = webRes.body.getReader();
                        var pump = function () {
                            reader.read().then(function (_a) {
                                var done = _a.done, value = _a.value;
                                if (done) {
                                    res.end();
                                    return;
                                }
                                res.write(value);
                                pump();
                            });
                        };
                        pump();
                    })
                        .catch(function (err) {
                        console.error("[analyze] handler error:", err);
                        res.writeHead(500, { "Content-Type": "application/json" });
                        res.end(JSON.stringify({ error: String(err) }));
                    });
                });
            });
        },
    };
}
export default defineConfig({
    plugins: [react(), netlifyFunctionsPlugin()],
    base: "/",
    server: { port: 5173 },
});
