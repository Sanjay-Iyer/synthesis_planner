# Demo data

> **Demo routes are illustrative examples intended to demonstrate the
> application's analysis workflow.** Chemical pathways and reagents may
> correspond to real chemistry, but demo yields, prices, sourcing assumptions,
> and route choices should not be interpreted as validated current industrial
> manufacturing data.

| File | What it is |
|---|---|
| `RouteA_PET.json` | Route A — PET via direct esterification of terephthalic acid (TPA) + ethylene glycol, GeO₂ catalyst (2 steps). Load into the Planner's Route A. |
| `RouteB_PET.json` | Route B — PET via transesterification of dimethyl terephthalate (DMT), Mn(OAc)₂ / Sb₂O₃ catalysts, solid-state polymerisation (3 steps). Load into Route B. |
| `setup/routeA_demo.txt`, `setup/routeB_demo.txt` | The same routes as free-text procedures, for the Setup (extraction) page. |
| `archive/` | Older example routes (CFBI variants) kept for reference. |
| `supply_chain/` | USITC trade data used by the Risk Audit — real data, see [`guide/DATA_SOURCES.md`](../guide/DATA_SOURCES.md). |

## Demo walkthrough: cost metrics vs. sourcing concentration

1. Planner → load `RouteA_PET.json` into Route A and `RouteB_PET.json` into
   Route B → **⚡ Run Analysis**. Compare total cost and E-factor.
2. **🌍 Analyze Risk** sends both routes' reagents (with production-scale costs
   and which route uses each reagent) to the Risk Audit.
3. The **Route Comparison** card shows each route's cost and E-factor next to
   its highest-concentration reagent, largest dominant-country share and the
   reagent cost grouped by dominant source country. There is no combined
   "best route" score — the decision is the user's.
4. In **Scenario / Shock Analysis**, try "Selected country supply interruption"
   for each dominant source country (with the current data: Mexico, South
   Korea, Canada, China) and compare how much of each route's reagent cost is
   affected.

The trade data is real (USITC / WITS); the routes' yields and prices are not.
Concentration results describe the reported trade for each HS6 product, not
the specific suppliers a real plant would use.
