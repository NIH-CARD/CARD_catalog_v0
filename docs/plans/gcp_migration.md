# Migration: Netlify → GCP (Firebase Hosting + Cloud Functions)

## Context
Migrate the CARD Catalog web app from Netlify to GCP within an existing Google Cloud org. The app has two parts: a static React/Vite SPA and one serverless function (`analyze.mjs`) that proxies the Anthropic API with SSE streaming.

## Target Architecture

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

---

## Files to Create

### `firebase.json` (project root)
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

### `.firebaserc` (project root)
```json
{ "projects": { "default": "<firebase-project-id>" } }
```

### `web/functions/package.json`
```json
{
  "name": "card-catalog-functions",
  "type": "module",
  "dependencies": { "firebase-functions": "^6.0.0" }
}
```

### `web/functions/index.mjs`
Thin wrapper — paste the entire body of `web/netlify/functions/analyze.mjs`, then replace the Netlify export with:

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

### `.github/workflows/deploy-web.yml`
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
          projectId: <firebase-project-id>
```

---

## Files to Modify

### `web/src/lib/useAnalysis.ts`
One-line change — update the fetch URL:
```diff
-  const response = await fetch("/.netlify/functions/analyze", {
+  const response = await fetch("/api/analyze", {
```

---

## Files to Remove (after migration confirmed)
- `web/netlify/functions/analyze.mjs`
- `netlify.toml`

---

## One-Time Setup (CLI)

```bash
# 1. Create GCP project
gcloud projects create card-catalog-web --organization=<ORG_ID>
gcloud config set project card-catalog-web

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

---

## Environment Variables

| Variable | Where | How |
|---|---|---|
| `ANTHROPIC_API_KEY` | Cloud Function | `firebase functions:secrets:set ANTHROPIC_API_KEY`, referenced via `secrets: ["ANTHROPIC_API_KEY"]` in `onRequest` config |
| `FIREBASE_SERVICE_ACCOUNT` | GitHub Actions | JSON key for the GCP service account |

---

## Verification

1. After `firebase deploy`, open the Firebase Hosting URL
2. Load any page → data displays (TSVs served from Firebase CDN)
3. Click **Analyze** → SSE text streams in (check Firebase Console → Functions for logs)
4. Push to `main` → GitHub Actions deploys automatically
5. Keep the old Netlify deploy live until the Firebase URL is confirmed working before cutting DNS

---

## Migration Sequence (low-risk order)

1. Create `firebase.json`, `web/functions/index.mjs`, `.firebaserc`
2. Test locally: `firebase emulators:start` — serves hosting + functions together
3. Deploy to Firebase (new URL, Netlify still live)
4. Smoke-test the Firebase URL end-to-end
5. Update `useAnalysis.ts` URL (`/api/analyze`) and re-deploy
6. Cut over DNS / custom domain
7. Disable Netlify
