# Bacheca — a personal research workbench for CARD Catalog

Status: **concept / future work**, not implemented. Nothing described here exists in
the current codebase — this doc exists so the idea isn't lost between now and the
planned v1 refactor (see `CLAUDE.md` "Current Status" and the paper's Future
Directions section).

## Naming

Working name: **Bacheca** — Italian for "bulletin board" / "pinboard": literally the
object a detective (or a librarian) pins things to and connects with string. More
direct than describing the corkboard metaphor secondhand, since it names the board
itself rather than a piece of it. No collision with domain jargon (unlike an earlier
draft, "The Study," which clashed with ELSA *Study*, the Religious Orders *Study*,
"most prolific studies," etc.). Alternates considered: **Redstring** (the pin-and-
thread image, English, more of a mood than an object) and **Card & String** (a nod
back to the Catalog's own name — a library card catalog's index drawers, plus the
detective's string — cuter but a weaker standalone product name).

## Motivation

Right now, every visit to the Catalog starts from zero: filters, search terms, and
any mental model of "which resources connect to which papers" live only in the
visitor's head and are gone when the tab closes. There's no way to save a specific
slice of the data, come back to it next week, or hand it to a collaborator by name.
The Catalog is good at *finding* connections (that's what the Connections/knowledge-graph
view already does today, per-session) but has no concept of a *user*, so nothing a
visitor builds persists or can be shared.

This concept adds a lightweight, opt-in layer on top of the existing read-only
Catalog: an account, a personal set of saved views, and a chat interface that can
talk about those saved views specifically — instead of only the whole corpus.

## Proposed capabilities

### 1. Accounts
A basic username-based registration/login, scoped only to identifying who saved what
— not a permissions system gating access to the underlying Catalog data, which stays
public. The bar here is "know whose saved queries these are," not "protect sensitive
data."

### 2. Saved queries and tables, addressable by name
A visitor can save the current state of a filtered table or query (the same filter/
search state already expressible via the app's facets, free-text search, and now
regex patterns — see `web/src/lib/filter.ts`, `web/src/components/FacetPanel.tsx`) 
under a name, scoped to their account: `username/name`. Later, they (or anyone they
share the name with) can reopen that exact slice — same filters, same search, same
sort — without reconstructing it by hand. This is closer to a saved SQL view than a
bookmark: it should be re-run against live data on load, not a frozen snapshot, so a
saved query for "ROSMAP publications from the last year" stays current as new
publications are ingested.

### 3. A chat interface that's aware of saved content
The Catalog already has an AI-analysis feature (`web/backend/main.py`,
`web/netlify/functions/analyze.mjs`) that can summarize a single row or a small
selection. This extends that idea: a more open-ended chat that can be pointed at a
saved query/table by name ("summarize what's changed in `pietro/rosmap-recent` since
last month," "what resources in `pietro/high-fair-datasets` are missing a DOI") and
reason over that specific, named slice rather than requiring the user to re-describe
it in every prompt. This is the main payoff of naming and saving content in the first
place — the name becomes a handle the chat can reference.

### 4. Question Index
A browsable list of example questions the chat interface can actually answer,
organized by table or topic (e.g. "which resources are missing a DOI," "how many
publications reference this gene," "summarize what changed in a saved query since
last month"). This exists because an open-ended chat box is intimidating when you
don't know its scope — the Question Index gives a visitor a starting point they can
pick and adapt, rather than staring at a blank prompt. It should stay in sync with
whatever the chat interface can actually do, rather than becoming its own
unmaintained wishlist.

## Open questions (not decided — flag for whoever picks this up)

- **Storage**: saved queries need a small persistence layer the Catalog doesn't have
  today (everything currently is `web/public/data/*.tsv`, static and client-fetched,
  with no server-side database). This likely can't be bolted onto the current
  Netlify-static + serverless-function architecture without adding a real backend
  data store.
- **Auth provider**: build vs. buy (e.g. a hosted auth provider) — not evaluated here.
- **Sharing model**: is `username/name` globally readable by anyone with the link
  (simplest), or private-by-default with explicit sharing? Given the underlying data
  is already public, the former is probably fine, but worth deciding deliberately
  rather than defaulting into it.
- **"Re-run live vs. frozen snapshot"** tension above: a live-updating saved query is
  more useful but harder to reason about when a collaborator says "the numbers
  changed since I looked at this" — may need an explicit "as of" timestamp shown
  alongside results either way.
- **Relationship to the provider-agnostic inference layer** already planned (see
  Future Directions) — the chat piece here should be built on top of that, not
  another one-off Anthropic-specific integration.

## Relationship to existing Future Directions

This is additive to, not a replacement for, the previously stated future work (cron-
automated updates, closing the residual repo-duplication gap, backfilling the 290
title-less publications, new-resource discovery, the provider-agnostic inference
layer). This doc covers a new, separate direction: turning the Catalog from a
read-only reference tool into a workbench visitors can build on top of.
