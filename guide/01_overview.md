# Synthesis Architect — Overview

## What It Is

**Synthesis Architect** is a locally-hosted web application for planning and comparing multi-step chemical synthesis routes and assessing reagent supply chain risk. It is designed for synthetic chemists, process chemists, and procurement teams who need to estimate costs, track waste metrics, optimize yields, and evaluate geographic sourcing vulnerabilities — all in one unified tool.

## Technology Stack

- **Backend**: Python with [FastAPI](https://fastapi.tiangolo.com/) (v2.0), served via Uvicorn
- **Frontend**: Vanilla HTML, CSS (Inter font from Google Fonts), and JavaScript with [Chart.js](https://www.chartjs.org/) for all visualizations
- **Molecular Tools**: [RDKit](https://www.rdkit.org/) for SMILES/InChI parsing and MW calculation, [SELFIES](https://github.com/aspuru-guzik-group/selfies) for SELFIES decoding, [PubChem PUG REST](https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest) for name resolution
- **Export Libraries**: [jsPDF](https://github.com/parallax/jsPDF) (loaded but not actively used), [JSZip](https://stuk.github.io/jszip/) for client-side ZIP generation of chart PNGs

## How to Launch

```bash
python start.py
```

This single command:
1. Changes to the project root directory
2. Starts a Uvicorn server on `http://localhost:8000` with `--reload` enabled for live development
3. Opens the app in your default browser (auto-detects WSL, macOS, and Linux)
4. Press `Ctrl+C` to stop

## Application Modules

The application has two major modules, accessible from a sticky dark navigation bar at the top of every page:

| Module | URL | Nav Label | Purpose |
|---|---|---|---|
| **Landing Page** | `/` | 🔬 Synthesis Planner (brand link) | Hub page with module cards linking to Planner and Risk Audit |
| **Synthesis Planner** | `/dashboard.html` | Planner | Route design, stoichiometry, cost analysis, yield optimization, procurement reporting |
| **Risk Audit** | `/risk.html` | Risk Audit | Geographic supply chain risk scoring and visualization |

## Project Structure

```
synthesis-architect/
├── start.py                          # One-command launcher
├── requirements.txt                  # Python dependencies (fastapi, uvicorn, pandas)
├── app/
│   ├── __init__.py
│   ├── main.py                       # FastAPI app setup, mounts routers, serves static files
│   ├── modules/
│   │   ├── __init__.py
│   │   ├── synthesis/
│   │   │   ├── __init__.py
│   │   │   ├── engine.py             # Stoichiometry, cost, E-factor, yield audit engine
│   │   │   └── router.py             # /api/synthesis/* endpoints
│   │   └── risk/
│   │       ├── __init__.py
│   │       ├── engine.py             # Multi-dimensional risk calculation engine
│   │       ├── router.py             # /api/risk/* endpoints
│   │       └── data/                 # CSV databases for CAS mappings and country stability
│   │           ├── reagent_mapping.csv
│   │           └── country_stability.csv
│   └── static/
│       ├── index.html                # Landing page
│       ├── dashboard.html            # Synthesis Planner page
│       ├── risk.html                 # Risk Audit page
│       ├── css/
│       │   └── styles.css            # Shared design system (Inter font, CSS variables, responsive grid)
│       └── js/
│           ├── dashboard.js          # All dashboard logic: step cards, stoichiometry, charts, export
│           └── risk.js               # Risk input, API calls, visualizations, export
├── data/                             # (Optional) user data files
├── archive/                          # (Optional) archived files
├── guide/                            # This documentation
└── *.json / *.yaml                   # Sample route files (e.g. Paracetamol routes)
```

## API Endpoints

All API endpoints are served from the same origin (`http://localhost:8000`):

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/synthesis/estimate` | Scale-up cost estimation for a synthesis route |
| `POST` | `/api/synthesis/audit` | Yield sensitivity audit (cost savings per 1% yield improvement) |
| `POST` | `/api/synthesis/molecule-name` | Resolve SMILES/SELFIES/InChI/InChIKey → chemical name via PubChem |
| `POST` | `/api/synthesis/molecular-weight` | Calculate MW via RDKit, PubChem, or formula parsing |
| `POST` | `/api/risk/assess` | Run full multi-dimensional risk assessment on a reagent list |
| `POST` | `/api/risk/update-mapping` | Save/update a CAS → Origin mapping to the server database |
| `GET`  | `/api/risk/mappings` | Fetch all current CAS → Origin mappings |

## Design System

The application uses a shared CSS design system (`styles.css`) with:
- **Font**: Inter (Google Fonts) with weights 300–700
- **Color palette**: Primary blue (`#0984e3`), secondary green (`#27ae60`), purple (`#8e44ad`), orange (`#f39c12`), danger red (`#e74c3c`)
- **Dark mode sections**: Dashboard results and charts render on `#1a1d23` / `#2d3436` backgrounds
- **Components**: Cards with shadows, pill badges for risk levels, step cards with colored left borders, responsive 2-column grid layout
- **Animations**: Fade-in transitions on page elements, hover lift effects on buttons and cards
