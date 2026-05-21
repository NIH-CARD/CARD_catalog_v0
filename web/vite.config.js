import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
// GitHub Pages serves the site at https://nih-card.github.io/CARD_catalog_v0/
// so we need a non-root base in production. Vite serves at "/" in dev.
var REPO = "CARD_catalog_v0";
export default defineConfig(function (_a) {
    var command = _a.command;
    return ({
        plugins: [react()],
        base: command === "build" ? "/".concat(REPO, "/") : "/",
        server: { port: 5173 },
    });
});
