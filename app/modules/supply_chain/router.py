"""
Supply-chain data router — exposes what trade data is indexed in the
supply-chain drop folder and lets the Risk Audit page look up an HS6.
"""

from fastapi import APIRouter

from . import provider

router = APIRouter(prefix="/api/supply-chain", tags=["supply-chain"])


@router.get("/status")
def supply_chain_status():
    """List the supply-chain data files currently indexed and their coverage."""
    return provider.get_status()


@router.post("/refresh")
def refresh_supply_chain():
    """Force a re-scan of the supply-chain folder (picks up newly added files)."""
    return provider.refresh()


@router.get("/lookup/{hs6}")
def lookup_hs6(hs6: str, year: int | None = None, ytd: bool = False):
    """Return the import concentration + export context for an HS6 code.

    The latest complete year is used by default; ``ytd=true`` explicitly opts
    into newer partial-year (year-to-date) data, which is labelled as such.
    """
    if year is not None:
        return {
            "concentration": provider.get_origin_concentration(hs6, year, allow_partial=ytd),
            "profile": provider.get_trade_profile(hs6, allow_partial=ytd),
        }
    return provider.get_trade_profile(hs6, allow_partial=ytd)
