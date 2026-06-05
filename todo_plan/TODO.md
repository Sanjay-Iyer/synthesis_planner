# Synthesis Architect — Master TODO

Organized by app section. Priority: **P1** = correctness / do-first, **P2** = quality
& UX, **P3** = nice-to-have. Checkboxes track status.

> Detailed sub-plans live in their own files in this folder and are linked inline.

---

## 1) Setup  (experiment.html · `app/modules/extraction`)

_Dedicated review pending — this section is scaffolding. The Setup tab parses
free-text procedures into route drafts via the Gemini extractor._

- [ ] **P2** Review the extraction pipeline (`gemini_extractor.py`, `service.py`) for
      prompt-injection handling, timeout/retry, and graceful degradation when the
      Gemini key is absent (the `/status` indicator exists — confirm the UI path).
- [ ] **P3** Surface `needs_review` fields prominently in the UI so users see exactly
      what the parser left blank before it flows into the Planner.
- [ ] **P3** Validate the `localStorage` handoff (`pendingRiskData` and any route
      draft) with a schema + version tag so a stale/older payload can't crash the
      receiving page.

---

## 2) Planner  (dashboard.html · `app/modules/synthesis`)

_Dedicated review pending — this section is scaffolding._

- [ ] **P2** Review `synthesis/engine.py` route math/validation and the dashboard
      JS for the same XSS/`alert()`/loading-state issues called out under Risk
      Assessment (they likely share patterns).
- [ ] **P3** Define a typed, versioned contract for the Planner → Risk Audit handoff
      instead of passing raw reagent JSON through `localStorage`.

---

## 3) Risk Assessment  (risk.html · `app/modules/risk`, `app/modules/supply_chain`)

Reviewed 2026-06-05. Findings below.

### 3a. Risk engine — correctness
- [ ] **P1** Skip aggregate "reporters" when auto-selecting origins. Trade data
      includes blocs like *European Union*, *Other Asia, nes*, *Areas, nes*. Today
      `run_risk_assessment` / `lookup_suggested_origins` can set a reagent's origin
      to one of these, which then misses the stability lookup and misleads the user.
      The provider already tags `reporter_type`; filter on it. (`risk/engine.py`)
- [ ] **P1** Replace risk-level **string parsing** with a structured tier. The
      summary `high_risk_count` uses `"HIGH" in level and "MEDIUM" not in level`
      and the frontend derives a CSS class from `level.split(' ')[0]`. Both break if
      the label text changes. Return a `risk_tier` enum (LOW/MEDIUM/MEDIUM_HIGH/HIGH)
      alongside the display label. (`risk/engine.py:433`, `risk.js` displayRiskResults)
- [ ] **P1** Don't silently **mutate the DB during assessment**. `run_risk_assessment`
      does `UPDATE compounds SET primary_origin…` + commit inside the per-reagent
      loop. Make persistence explicit (separate endpoint / flag) so a read-style
      assessment has no side effects. (`risk/engine.py:~338`)
- [ ] **P2** **One DB connection per assessment**, not one per reagent. Currently
      `connect_db()` is called inside the loop (`risk/engine.py:320`); open once,
      pass it down. Also cache the `PRAGMA table_info(compounds)` schema check
      instead of running it every reagent.
- [ ] **P2** **Cache reference tables.** `load_reagent_mapping()` and
      `load_country_stability()` read CSV from disk on every call (several times per
      request) and *write a default file as a side effect of reading*. Load once /
      memoize; separate seeding from reading.
- [ ] **P2** **Extract a shared `resolve_hs6(name, cas)`** helper. The CAS→mapping →
      name-hint → DB resolution logic is duplicated between `lookup_suggested_origins`
      and `run_risk_assessment`. DRY it and unit-test it.
- [ ] **P2** **Externalize the risk model.** Weights (0.30/0.20/0.30/0.20),
      thresholds (150/100/50), and multipliers (×1.5 opacity, hazard×4+reg×6,
      log-exposure) are magic numbers in code. Move to a documented config block with
      rationale, then add unit tests pinning the math.
- [ ] **P2** Move `CRITICAL_CAS` / `REGULATORY_CAS` out of code into data files (like
      `reagent_mapping.csv`) so they can be maintained without a deploy, and expand
      beyond the current demo handful.
- [ ] **P2** Validate / clamp advanced inputs (hazard, regulatory, substitutability
      expected 1–10; mass/cost ≥ 0) in the Pydantic model.
- [ ] **P3** Replace bare `except:` (`risk/engine.py:178`) and the broad swallow in
      `get_supply_chain_concentration` with specific exceptions + logging.
- [ ] **P3** Standardize on Pydantic v2 and drop the `model_dump()`/`.dict()` straddle
      (`risk/engine.py:473`); pin the version in `requirements.txt`.

### 3b. Supply-chain data (USITC integration)
- See **[stability_score_expansion.md](stability_score_expansion.md)** — expand the
  country-stability table and add a country-name alias layer (USITC "South Korea" vs
  WGI "Korea, Rep.", "Russia" vs "Russian Federation", "Taiwan" vs "Chinese Taipei").
- [ ] **P1** **Minimum-coverage guard for partial-year data.** Jan-2026 has very thin
      country coverage, so most HTS6 currently resolve to a 1–2-country snapshot and
      read as ~90–100% concentrated. Require a minimum reporting-country count (or
      minimum total value) before trusting a year; otherwise fall back to the latest
      full year. (`supply_chain/provider.py` `_pick_year`)
- [ ] **P2** Report **HHI (Herfindahl index)** across *all* countries, not just the
      top-1 share — the standard concentration metric; less sensitive to thin data.
- [ ] **P2** Add a **multi-year concentration trend** (is reliance on the top source
      rising or falling 2020→2025?) — far more actionable than a single year.
- [ ] **P2** Compute **net trade position** from imports + exports (net importer =
      dependent/higher risk; net exporter = resilient) and factor it into the score.
- [ ] **P3** Normalize countries to **ISO3** (`reporter_iso3` is currently `None`) to
      enable a world-map visualization and clean joins to WGI/stability data.
- [ ] **P3** Vectorize the index build (pandas groupby) instead of `iterrows()` over
      ~26k rows; it's cached, so low urgency, but cleaner.
- [ ] **P3** Document the cache model (process-local, no TTL): with multiple uvicorn
      workers each rebuilds independently. Fine for now — note it.

### 3c. API
- [ ] **P2** Validate the `hs6` path param format in `/api/supply-chain/lookup/{hs6}`
      and return structured error codes from `/api/risk/assess` (the frontend
      currently `JSON.stringify`s whatever comes back).
- [ ] **P3** Add a request-size limit / pagination guard on `/assess` (nothing stops
      a multi-thousand-reagent payload).

### 3d. Frontend (risk.html / risk.js)
- [ ] **P1** **Remove the duplicate `chart.js` include** — it's loaded twice
      (`risk.html:8` and `risk.html:269`).
- [ ] **P1** **Robust CSV parsing.** `loadCSV` uses `line.split(',')`, which corrupts
      any quoted field containing a comma (descriptions, "Company, Inc."). Use a real
      parser (e.g. PapaParse) or a proper CSV tokenizer.
- [ ] **P2** **Escape user-supplied content.** Reagent names/descriptions are injected
      via `innerHTML` in the results table and heatmap → XSS / layout breakage from
      uploaded CSVs. Use `textContent`/`createElement` or escape. Also escape quotes
      when building the export CSV (`exportRiskCSV`).
- [ ] **P2** Add a **loading state** to "Run Risk Assessment" (only Auto-Lookup has
      one) and replace blocking `alert()` calls with inline toasts/messages.
- [ ] **P3** **Show origin provenance** per reagent ("origin set from USITC Imports
      2024, 62% share") so users understand why an origin was chosen and can override.
- [ ] **P3** Accessibility: the heatmap encodes risk by color only — add labels/ARIA
      and check contrast.

### 3e. Testing & data coverage
- [ ] **P1** Add unit tests for: the risk math, the USITC parser
      (`supply_chain/usitc_ingest.py`), and the concentration/year-selection logic.
      `tests/` already exists (extraction tests) — extend it.
- [ ] **P2** Expand `compound_hs6_map.json` (only 5 entries today) and
      `reagent_mapping.csv` so most reagents actually resolve to an HTS6; without a
      mapping, no supply-chain data is found regardless of how good the data is.

---

## Cross-cutting / infrastructure
- [ ] **P2** `__pycache__` / `.pyc` files are **tracked in git** (visible in
      `git status`). The new untracked `.gitignore` should exclude them; untrack the
      committed ones.
- [ ] **P2** Restrict **CORS** before any non-local deployment (currently
      `allow_origins=["*"]`, all methods/headers — `app/main.py`).
- [ ] **P3** Establish a logging setup (structured, leveled) — several modules use
      `print()` or swallow errors.
