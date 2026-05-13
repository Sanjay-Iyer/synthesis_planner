# Database Integration (Completed) — Synthesis Architect

A robust, professional SQLite-backed database system has been integrated into Synthesis Architect. This system provides persistent storage for compounds, synthesis routes, and analysis runs, replacing the originally proposed flat JSON database.

---

## Final Implementation Overview

The system transitions the application from temporary in-memory analysis to a persistent molecular registry and route history.

### 1. Database Architecture
**Location:** `/home/sanjay/AV/synthesis-architect/database/synthesis_architect.db`

The database uses **SQLite 3** with the following professional features:
- **Transactional Integrity:** All route saves use atomic transactions (BEGIN/COMMIT). If a reagent save fails, the entire route save is rolled back.
- **High Concurrency:** Enabled via `PRAGMA journal_mode=WAL` (Write-Ahead Logging), allowing simultaneous reads while saving data.
- **Immutable Source Data:** The original route JSON files (e.g., `RouteA_PET.json`) are treated as immutable templates and are **never modified** by the database system. UUID mappings are stored entirely within SQLite.

### 2. Multi-Tier Compound Deduplication
The system implements a **4-tier deduplication logic** to ensure molecular integrity:

1. **Canonical SMILES** (High Confidence): Uses RDKit to normalize SMILES strings. Most reliable.
2. **InChIKey** (High Confidence): Unique molecular fingerprint generated via RDKit.
3. **SELFIES** (Medium Confidence): Alternative molecular string representation.
4. **Normalized Name** (Low Confidence): Case-insensitive, whitespace-stripped name matching (last resort).

### 3. Route Hashing & Deduplication
To prevent duplicate route definitions while allowing multiple analysis runs:
- A **SHA256 Route Hash** is computed based on the target molecule and the content of every step (names, reagents, stoichiometry, conditions).
- If a route with the same hash is saved again, the system **reuses the existing route UUID** and merely adds a new entry to the `analysis_runs` table.
- This allows tracking how costs change over time or for different target masses (e.g., 3 kg vs 10 kg) for the exact same chemistry.

---

## Database Schema

| Table | Purpose |
|-------|---------|
| `compounds` | Registry of unique chemical entities with RDKit-derived properties (MW, Formula, InChIKey). |
| `routes` | Metadata for saved synthesis pathways, uniquely identified by hash. |
| `route_steps` | Individual steps within a route, linked via `route_uuid`. |
| `step_reagents` | All reagents, catalysts, and additives used in a step, mapped to `compounds.uuid`. |
| `analysis_runs` | Records of specific analysis results (Cost, E-Factor) tied to a route. |
| `metadata` | Internal versioning and system configuration. |

---

## API Endpoints (`/api/database/`)

- `POST /save-route`: Persists active UI state to the database. Returns counts of new vs updated compounds.
- `POST /validate-route`: Dry-run that returns what the database impact *would* be without writing data.
- `GET /compounds`: Searchable molecular registry.
- `GET /routes`: History of all saved synthesis routes.
- `GET /summary`: High-level metrics (total compounds, reuse frequency, recent activity).

---

## Frontend Integration

The **"💾 Add to Database"** button in the toolbar is the primary entry point:
1. **Unlocks** automatically after a successful analysis run.
2. **Batch Saves:** Both Route A and Route B are saved simultaneously.
3. **Toast Feedback:** Real-time notifications report exactly how many new compounds were registered and if any "Ambiguous" compounds (vague names without structures) need review.

---

## Verification & Maintenance

### Running Tests
A full backend test suite is available:
```bash
cd /home/sanjay/AV/synthesis-architect
python3 -m pytest tests/test_database.py
```

### Manual Inspection
You can inspect the database content directly:
```bash
sqlite3 /home/sanjay/AV/synthesis-architect/database/synthesis_architect.db "SELECT name, reuse_count FROM compounds_summary_view" # (example)
```
