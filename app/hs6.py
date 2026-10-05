"""Shared HS6 input handling. A code identifies a trade category, not a chemical."""

import re
from typing import Annotated, Optional

from pydantic import BeforeValidator


def hs6_text(value) -> Optional[str]:
    """Keep input as text, including invalid values so the audit can flag them."""
    if value is None:
        return None
    return re.sub(r"\s+", "", str(value)) or None


def normalize_hs6(value) -> Optional[str]:
    """Accept exactly six ASCII digits; never truncate, pad or strip punctuation."""
    text = hs6_text(value)
    return text if text and re.fullmatch(r"[0-9]{6}", text) else None


# Invalid explicit inputs remain visible and block automatic resolution.
HS6Input = Annotated[Optional[str], BeforeValidator(hs6_text)]
