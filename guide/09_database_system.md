# 09: Persistent Database System

Synthesis Architect utilizes a persistent **SQLite** database to manage chemical knowledge and synthesis history. This system moves the application beyond single-session analysis, enabling cross-route comparison and long-term data tracking.

---

## 1. The SQLite Backend

The database file is located at:
`/home/sanjay/AV/synthesis-architect/database/synthesis_architect.db`

### Key Design Principles:
- **Atomicity:** All data related to a route (steps, reagents, results) is saved in a single database transaction. This prevents partial or corrupted records.
- **Deduplication:** The system automatically recognizes if a compound or route has been seen before.
- **Extensibility:** The schema is designed for future integration with AI agents (like LangChain SQL tools) to allow natural language querying of chemical data.

---

## 2. Compound Deduplication

When a route is saved, every reagent undergoes a 4-tier check to see if it already exists in the registry:

| Tier | Basis | Confidence |
|------|-------|------------|
| 1 | **Canonical SMILES** | High |
| 2 | **InChIKey** | High |
| 3 | **SELFIES** | Medium |
| 4 | **Normalized Name** | Low |

> [!TIP]
> **RDKit Integration:** If RDKit is installed on the server, the system automatically generates Canonical SMILES and InChIKeys for all reagents, ensuring extremely high deduplication accuracy.

---

## 3. Route Hashing

Routes are uniquely identified by a **SHA256 Hash**. This hash is calculated from the chemistry of the route (steps, reagents, amounts) but excludes metadata like timestamps or target mass.

- **Reusing Routes:** If you analyze the exact same route at 3 kg and then at 10 kg, the system recognizes it as the same chemistry and simply adds a new "Analysis Run" record under the existing Route entry.
- **New Routes:** Any change to the chemistry (adding a step, changing a reagent, modifying a yield) generates a new hash and a new Route entry.

---

## 4. Ambiguous Compounds

A compound is flagged as **Ambiguous** if:
- It has no molecular structure (SMILES/SELFIES).
- Its name is generic (e.g., "Intermediate", "Stabilizer", "Catalyst Slurry").

Ambiguous compounds are still saved to ensure cost calculations remain accurate, but they are flagged in the UI toast notification to alert the user that they may need better identification for future runs.

---

## 5. Developer API

| Endpoint | Method | Result |
|----------|--------|--------|
| `/api/database/save-route` | `POST` | Saves route + current results. |
| `/api/database/validate-route` | `POST` | Previews the save impact. |
| `/api/database/summary` | `GET` | Returns high-level DB metrics. |
| `/api/database/compounds` | `GET` | Lists the molecular registry. |

### Example Summary Response:
```json
{
  "compound_count": 142,
  "route_count": 12,
  "analysis_run_count": 45,
  "ambiguous_compound_count": 8
}
```
