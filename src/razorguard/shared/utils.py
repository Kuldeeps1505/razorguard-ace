# shared/utils.py
from decimal import Decimal


def paise_to_rupees(paise: int) -> Decimal:
    """Convert integer paise to Decimal rupees. Never use float."""
    return Decimal(paise) / Decimal(100)


def rupees_to_paise(rupees: Decimal) -> int:
    """Convert Decimal rupees to integer paise."""
    return int(rupees * 100)


def mask_id(value: str, visible: int = 4) -> str:
    """Mask a sensitive ID for logging. e.g. 'abc123xyz' → '****xyz'"""
    if len(value) <= visible:
        return "****"
    return "*" * (len(value) - visible) + value[-visible:]
