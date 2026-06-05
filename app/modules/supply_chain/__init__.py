"""
Supply-chain data module.

Live-scans the supply-chain data drop folder (``data/supply_chain``) for trade
data files — currently USITC DataWeb exports — and exposes per-HTS6 origin
concentration metrics used by the Risk Audit page. Drop a new compatible file
into the folder and it is picked up automatically on the next lookup; no manual
ingest step is required.
"""
