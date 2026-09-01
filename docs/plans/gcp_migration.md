# CARD Catalog — GCP Migration

## Context

CARD Catalog's data currently lives entirely as git-committed flat files: the pipeline (`orchestrator.py` + `pipelines/*.py` + `staging/normalizer.py`) writes validated TSVs to `tables/final/`, and the React SPA (`web/`) fetches those TSVs client-side (papaparse) with all filtering done in the browser. This surfaced as a real problem in practice: `scilite_annotations.tsv` (250MB+ and growing) already gets flagged as a scaling risk in `web/README.md`, and there's no automation at all — `orchestrator.py` has only ever been run manually on a laptop, despite `docs/getting_started.md`/`docs/overview.md` documenting an intended (never-deployed) crontab schedule. The app is also hosted on Netlify today, deployed separately from everything else.

The goal is to move everything onto GCP: all pipeline output tables into Cloud SQL Postgres (not a hybrid — every table, including the small ones), the web app's data loading rewritten to query a real backend API instead of shipping whole TSVs to the browser, the pipeline itself running on a schedule via Cloud Run + Cloud Scheduler instead of a human's laptop, and the web app hosted on GCP (Firebase Hosting + Cloud Functions) instead of Netlify. This is a five-phase migration; phases are staged so the live site never breaks mid-migration.

## Current state (confirmed this session)

- **Pipeline**: `staging/schemas.py`'s `SCHEMA_REGISTRY` maps target names → Pydantic row models with `COLUMNS: ClassVar[list[str]]`. `staging/normalizer.py::normalize(input_path, target, output_path)` validates and writes to `tables/final/<target>_<ts>.tsv`, deleting older files for that target. Multi-value fields (diseases, modalities, authors, languages) are semicolon-delimited strings in a single TSV cell.
- **Web app**: `web/src/lib/loaders.ts` has per-table loaders, each `loadTsv("/data/<file>.tsv")` (fetch → papaparse, no caching). Filtering/faceting (`web/src/lib/filter.ts`, `useFacets.ts`) runs entirely client-side after the full table loads. `web/backend/main.py` (FastAPI) + its Dockerfile exist but are **dead code** — nothing calls them today.
- **No existing automation**: no Dockerfile for the pipeline, no cron/Cloud Scheduler, no CI beyond a docs-only GitHub Pages workflow.
- **`page_navigation` stage** drives headless Firefox via Selenium against a pre-authenticated profile dir (`FIREFOX_PROFILE_DIR`) — a real, unresolved containerization risk (see Phase 4).
- **Web hosting today**: Netlify, with one serverless function (`web/netlify/functions/analyze.mjs`) that proxies the Anthropic API with SSE streaming for the app's AI-analysis feature.

## Setup status (2026-08-25)

- **Org**: `datatecnica.com` (ID `1058982408881`) — confirmed available via `gcloud organizations list`.
- **Project**: created — `card-catalog-506619` (console: `console.cloud.google.com/welcome/new?project=card-catalog-506619`). One project for the whole migration, not split per phase.
- **Region**: a US region (e.g. `us-central1`) — CARD Catalog is US NIH/NIA-funded infrastructure; the machine's current `gcloud` default (`europe-west4`) was rejected for this project.
- **Billing**: unblocked for now — a personal GCP free-trial billing account is linked to `card-catalog-506619`, to allow early Phase 1 development/testing (small-scale Cloud SQL + Cloud Run work) while DataTecnica's org billing account request to whoever manages it is still pending. Swapping to the org billing account later (once approved) is a one-step change in GCP Console → Billing, no data loss or project recreation needed. Treat the free-trial account as dev-only, not where production traffic should ever run — trial accounts expire/have credit caps, and a personal account is the wrong long-term owner for NIH-funded infrastructure.
- **Decision**: unpaused — Phase 1 work can start now against this project using the trial billing account.

## Phase 1 — Postgres schema + dual-write

**Schema mapping**: one Postgres table per `SCHEMA_REGISTRY` target (`misc_publications`, `pub_datasets`, `pub_grants`, `supplementary`, `pub_software`, `pub_models`, `code`, `new_corpus`, `scilite`, plus `resources` and `cellular_models` which don't currently go through the normalizer — add them). Columns come directly from each Pydantic model's `COLUMNS`.

**Multi-value fields → native `text[]` array columns**, not normalized join tables. Reasoning: normalizing into join tables would require redesigning every filter query and the facet-count logic from scratch; `text[]` preserves near-identical semantics to today's semicolon-split (`value.split(';')` → array literal), and Postgres supports GIN indexes + array-containment operators (`@>`, `= ANY()`) that map directly onto "filter by disease X" faceted search. Lower risk, less rework, matches how the app already thinks about these fields.

**Normalizer change**: `staging/normalizer.py::normalize()` gets a new write path — instead of (initially: in addition to) writing the final TSV, it writes the validated DataFrame to its Postgres table via SQLAlchemy, using a full-replace strategy (`CREATE TABLE ... AS SELECT` into a staging table, then atomic rename/swap) that mirrors the current "one file per target, delete the old one" behavior — each run fully replaces that target's table.

**Dual-write during transition**: keep writing the TSV to `tables/final/` *and* write to Postgres. This means the current web app keeps working unmodified while Postgres gets populated and the new API is built/tested against it, with zero risk to the live site. Drop the TSV write only after full cutover (Phase 3).

**Cloud SQL connection from the pipeline**: use Cloud Run Jobs' built-in Cloud SQL integration (attach the instance to the job; it exposes a Unix socket at `/cloudsql/<INSTANCE_CONNECTION_NAME>`) rather than a Cloud SQL Auth Proxy sidecar or the Python Connector library — it's the simplest, most idiomatic pattern for Cloud Run specifically. Connection string: `postgresql+psycopg2://<user>:<password>@/<dbname>?host=/cloudsql/<INSTANCE_CONNECTION_NAME>`, password from Secret Manager.

**`tables/hits/` stays as local/ephemeral files, unchanged** — it's never served to anyone, purely an internal handoff between pipeline stages and the normalizer; no reason to move it anywhere.

## Phase 2 — New backend query API

**Repurpose `web/backend/main.py`'s FastAPI scaffold** — it already has FastAPI, a Dockerfile, and a CORS allow-list including `alzheimersdatahub.org`. Strip out the (dead, unused) AI-analysis logic — that capability properly lives in the Firebase Cloud Function per Phase 5 — and turn this into the query API instead. Reusing the scaffold avoids starting from zero and keeps the "Python backend for data, Node function for AI proxy" split clean.

**Deploy as its own Cloud Run *service*** (not a Job — it needs to be always-reachable and request-driven, and Cloud Run services scale to zero when idle, which matters given Cloud SQL's own always-on cost, see Cost callouts).

**Endpoints**: one per table (`/api/publications`, `/api/pub_datasets`, `/api/pub_grants`, `/api/pub_supplementary`, `/api/pub_software`, `/api/pub_models`, `/api/code`, `/api/cellular_models`, `/api/resources`, `/api/scilite_annotations`), each supporting filter query params matching current facet dimensions (disease, modality, resource name, etc.) and pagination. Also needs facet-count endpoints (e.g. `/api/publications/facets?field=diseases` → distinct values + counts within the current filter set) — this is the real, non-trivial part of the backend work, since it's porting `useFacets.ts`'s logic into SQL `GROUP BY` queries.

**Routing from the SPA**: add a second Firebase Hosting rewrite rule (Firebase Hosting supports rewriting directly to a Cloud Run service, not just Cloud Functions) so the query API is reachable at a same-origin relative path (e.g. `/api/data/**` → the Cloud Run service), avoiding CORS entirely — consistent with how Phase 5 already handles `/api/analyze`.

## Phase 3 — Web app rewrite (phased, not all at once)

Filtering **moves server-side** as part of this rewrite — an API that just returns "everything" for client-side filtering would ship the same bytes as today's TSV and defeat the point of the migration.

Cutover order, each step shippable independently while everything else keeps working on the old path:
1. Migrate the smallest/simplest page first (`ResourcesPage.tsx`, backed by `resources.tsv`) as the pattern-setter: new loader (in `web/src/lib/api.ts` or alongside `loaders.ts`) calling the new API, `useFacets.ts` logic for that page ported server-side.
2. Migrate remaining pages one at a time, prioritizing `AnnotationsPage.tsx`/scilite_annotations last-to-hardest-but-highest-value (the actual motivating pain point, given that table's size).
3. `DataTable`/`FilterRail` components' props likely don't need to change much — they already take "current rows" + "facet definitions with counts"; only *where* those come from changes (API response vs. client-computed `useMemo`).
4. Once every page is migrated, delete `sync-data.sh`'s TSV-copying (keep only the logo/synonym-JSON copies, which have no Postgres equivalent), and drop the normalizer's TSV write path from Phase 1.

**Note on Phase 5's ordering**: Phase 5 (web hosting cutover) is technically independent and could run before Phase 3 — but if it does, Firebase Hosting will serve TSVs from `public/data/` exactly as Netlify does today (see Phase 5's verification step). Once Phase 3 completes, Firebase Hosting only needs to serve the built `web/dist/` SPA bundle plus the `/api/analyze` and `/api/data/**` rewrites — no TSVs at all.

## Phase 4 — Pipeline orchestration (Cloud Run Jobs + Cloud Scheduler)

**One Cloud Run Job definition**, parameterized by the orchestrator mode (`update` vs `full_rebuild`) via container args overridden per invocation, rather than two separate job definitions.

**Cron scheduling gotcha (real correctness issue, not hand-waved)**: the documented schedule ("first Monday of Jan/Apr/Jul/Oct") relied on a shell conditional (`[ "$(date +%u)" = "1" ]`) in the original crontab precisely because standard cron OR's its day-of-month and day-of-week fields rather than AND-ing them — `0 12 1-7 1,4,7,10 1` would fire on *any* day 1-7 of those months *or* any Monday, not their intersection. Cloud Scheduler's cron parser has the same semantics. Fix: schedule Cloud Scheduler simply as "every Monday in Jan/Apr/Jul/Oct" (`0 12 * 1,4,7,10 1`), and move the "is today in the first 7 days of the month" check into the container's own entrypoint — it exits cleanly (no-op) on the three non-first Mondays. The `update` job schedules as a plain "every Monday" (`0 12 * * 1`), no such issue.

**Dockerfile**: base image with `requirements.txt` deps + `pip install` of the internal `data_gatherer` package (needs a git credential or private PyPI access wired into the build — likely via Secret Manager-backed Cloud Build config).

**`page_navigation`'s Selenium/Firefox stage — open risk, not solved here**: it needs a Firefox+geckodriver-capable image, but its `FIREFOX_PROFILE_DIR` is a *pre-authenticated* profile (session cookies from an interactive login) that doesn't transplant cleanly into a fresh container — IP/fingerprint changes can invalidate sessions, and "fully automated" is in tension with "needs periodic human re-authentication." Two real options, no silent third way: (a) exclude `page_navigation` from the scheduled Cloud Run Job entirely and keep running it manually/locally as before, or (b) mount a GCS-synced profile directory into the job and accept an ongoing manual re-auth maintenance task. This needs a decision before Phase 4 ships — flagging it here rather than assuming.

**Secrets**: `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, `NCBI_API_KEY`, and the new Postgres credentials all via Secret Manager, wired to the Cloud Run Job via `--set-secrets`.

## Phase 5 — Web hosting (Netlify → Firebase Hosting + Cloud Functions)

Migrates the web app's *hosting* off Netlify. Technically independent of Phases 1-4 (could run first or last) — see the ordering note at the end of Phase 3 for what changes about this phase depending on when it runs relative to Phase 3. As a matter of sequencing preference, do this phase last, to keep the number of simultaneously-changing systems low; the one hard constraint is the **DNS cutover step below, which must wait until the full migration (whichever phases have run) is validated end-to-end** — keep the old Netlify deploy live until then.

### Target architecture

```
Firebase Hosting (CDN)          Firebase Cloud Functions 2nd gen
      │                                       │
      │  static SPA (dist/)                   │  analyze function
      │  + SPA fallback routing               │  (analyze.mjs adapted)
      │                                       │
      └────── /api/analyze (rewrite) ─────────┘
```

- **Firebase Hosting**: serves `web/dist/`, global CDN, all unmatched routes → `index.html`
- **Firebase Cloud Functions (2nd gen)**: wraps the existing `analyze.mjs` logic
- **Firebase Hosting rewrite**: `/api/analyze` → the Cloud Function (keeps URL relative, avoids CORS)
- **GitHub Actions**: replaces Netlify's auto-deploy; one workflow builds and deploys both

### Files to create

**`firebase.json`** (project root):
```json
{
  "hosting": {
    "public": "web/dist",
    "ignore": ["firebase.json", "**/.*"],
    "rewrites": [
      { "source": "/api/analyze", "function": "analyze" },
      { "source": "**", "destination": "/index.html" }
    ]
  },
  "functions": {
    "source": "web/functions",
    "runtime": "nodejs20"
  }
}
```

**`.firebaserc`** (project root):
```json
{ "projects": { "default": "card-catalog-506619" } }
```

**`web/functions/package.json`**:
```json
{
  "name": "card-catalog-functions",
  "type": "module",
  "dependencies": { "firebase-functions": "^6.0.0" }
}
```

**`web/functions/index.mjs`** — thin wrapper — paste the entire body of `web/netlify/functions/analyze.mjs`, then replace the Netlify export with:
```js
import { onRequest } from "firebase-functions/v2/https";

// ... all existing constants and functions (ANTHROPIC_API_KEY, formatters, prompts) ...

export const analyze = onRequest(
  { timeoutSeconds: 120, memory: "256MiB", secrets: ["ANTHROPIC_API_KEY"] },
  async (req, res) => {
    // paste existing handler body here unchanged
    // req/res is identical to Node.js http — SSE streaming works as-is
  }
);
```
The existing `res.setHeader(...)`, `res.write(...)`, `res.end()` pattern works unchanged with Cloud Functions 2nd gen.

**`.github/workflows/deploy-web.yml`**:
```yaml
name: Deploy Web to Firebase

on:
  push:
    branches: [main]
    paths: ["web/**", "tables/**"]
  workflow_dispatch:

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20" }

      - name: Install and build
        working-directory: web
        run: npm ci && npm run sync-data && npm run build

      - name: Install functions deps
        working-directory: web/functions
        run: npm ci

      - uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: ${{ secrets.WIF_PROVIDER }}
          service_account: ${{ secrets.WIF_SERVICE_ACCOUNT }}

      - uses: FirebaseExtended/action-hosting-deploy@v0
        with:
          repoToken: ${{ secrets.GITHUB_TOKEN }}
          firebaseServiceAccount: ${{ secrets.FIREBASE_SERVICE_ACCOUNT }}
          channelId: live
          projectId: card-catalog-506619
```

### Files to modify

**`web/src/lib/useAnalysis.ts`** — one-line change, the fetch URL:
```diff
-  const response = await fetch("/.netlify/functions/analyze", {
+  const response = await fetch("/api/analyze", {
```

### Files to remove (after migration confirmed)

- `web/netlify/functions/analyze.mjs`
- `netlify.toml`

### One-time setup (CLI)

Uses the **same** GCP project as the rest of the migration — `card-catalog-506619` (org `datatecnica.com`, ID `1058982408881`) — not a separate project. Already created, see "Setup status" above.

```bash
# 1. Project already created — just point gcloud at it
gcloud config set project card-catalog-506619

# 2. Enable billing (required for Cloud Functions)
# GCP Console → Billing → Link billing account

# 3. Initialize Firebase
npm install -g firebase-tools
firebase login
firebase init   # select: Hosting + Functions, use existing project

# 4. Store the Anthropic secret
firebase functions:secrets:set ANTHROPIC_API_KEY
# paste the key when prompted

# 5. First deploy
firebase deploy

# 6. GitHub Actions secret
# GCP Console → IAM → Service Accounts → create SA with roles:
#   Firebase Admin, Cloud Functions Admin, Service Account User
# Download JSON key → add as FIREBASE_SERVICE_ACCOUNT GitHub secret
```

### Environment variables

| Variable | Where | How |
|---|---|---|
| `ANTHROPIC_API_KEY` | Cloud Function | `firebase functions:secrets:set ANTHROPIC_API_KEY`, referenced via `secrets: ["ANTHROPIC_API_KEY"]` in `onRequest` config |
| `FIREBASE_SERVICE_ACCOUNT` | GitHub Actions | JSON key for the GCP service account |

### Phase 5 verification

1. After `firebase deploy`, open the Firebase Hosting URL.
2. Load any page → data displays. **If Phase 3 hasn't landed yet**, this means TSVs served from Firebase CDN (same model as Netlify today); **if Phase 3 has landed**, this means the SPA calling the Cloud Run query API instead — either way, confirm the page actually renders data.
3. Click **Analyze** → SSE text streams in (check Firebase Console → Functions for logs).
4. Push to `main` → GitHub Actions deploys automatically.
5. Keep the old Netlify deploy live until the Firebase URL is confirmed working before cutting DNS.

### Phase 5 migration sequence (low-risk order)

1. Create `firebase.json`, `web/functions/index.mjs`, `.firebaserc`.
2. Test locally: `firebase emulators:start` — serves hosting + functions together.
3. Deploy to Firebase (new URL, Netlify still live).
4. Smoke-test the Firebase URL end-to-end (see Phase 5 verification above).
5. Update `useAnalysis.ts` URL (`/api/analyze`) and re-deploy.
6. **Cut over DNS / custom domain** — only once the *entire* planned migration (whichever of Phases 1-4 are in scope for this cutover) is validated, not right after step 5 alone. Coordinate with ADDI (Caitlin McHugh) to repoint `alzheimersdatahub.org`.
7. Disable Netlify.

## Cost/complexity callouts

- **Cloud SQL Postgres has a real, recurring cost** even at the smallest tier and near-zero traffic (roughly $10-50/month) — this is a genuine tradeoff against the current $0 marginal cost of git-committed flat files, worth being explicit about rather than assuming "it's just GCP, it's cheap."
- Cloud Run (both the query API service and the pipeline Job) and Cloud Scheduler are pay-per-use/scale-to-zero — cheap, no idle cost.
- Firebase Hosting + Cloud Functions at this traffic level are very likely within GCP's free tier.
- The single biggest complexity/risk item in the whole migration is `page_navigation`'s containerization (Phase 4) — it needs an explicit decision, not a default assumption that it "just works."

## Verification

- **Phase 1**: after dual-write lands, spot-check row counts and a sample of rows in each Postgres table against the corresponding `tables/final/*.tsv` to confirm the write path is correct before anything depends on it.
- **Phase 2**: exercise every new endpoint directly (curl/Postman) against the populated tables — confirm filter and facet-count responses match what the current client-side `useFacets.ts` computes for the same filter combinations, before wiring up any frontend.
- **Phase 3**: after each page's migration, manually verify that page's filters/facets/row counts match the pre-migration (TSV-based) version exactly, page by page — this is the actual regression-testing strategy given there's no existing test suite for this UI.
- **Phase 4**: trigger both Cloud Run Job modes manually (`gcloud run jobs execute`) before trusting Cloud Scheduler, confirm Postgres tables update as expected, and confirm the "first Monday" no-op logic actually skips on non-first Mondays.
- **Phase 5**: see Phase 5's own verification subsection above — Firebase URL smoke test, SSE streaming check, GitHub Actions auto-deploy check, before cutting DNS.
