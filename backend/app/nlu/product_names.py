"""Product names in the languages added in 2.3.0, keyed by SKU.

The 65 staple SKUs of the demo catalogue have a display name and spoken aliases in Marathi, Bengali, Tamil, Telugu,
Kannada, Malayalam and Punjabi (``nlu/langpacks/<lang>.py``). A product the shopkeeper adds later has no entry here:
it is recognised by the names and aliases typed on its catalogue row (any language), and spoken back by its English name.
"""
from __future__ import annotations

from functools import lru_cache

from .langpacks import load_all


@lru_cache(maxsize=1)
def _table() -> dict[str, dict[str, list[str]]]:
    out: dict[str, dict[str, list[str]]] = {}
    for lang, pack in load_all().items():
        for sku, raw in pack.names.items():
            out.setdefault(sku, {})[lang] = [n.strip() for n in raw.split("|") if n.strip()]
    return out


def names_for(sku: str) -> dict[str, list[str]]:
    """{language: [display name, alias, ...]} for a SKU, or {} for a product that is not one of the staples."""
    return _table().get(sku, {})
