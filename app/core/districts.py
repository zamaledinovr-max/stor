"""Fixed list of districts accepted by the catalog.

The list is deliberately hard-coded: users pick a district from a selector and
the server re-validates the value against this list on every write.
"""

from __future__ import annotations

DISTRICTS: tuple[str, ...] = (
    "Московский тракт",
    "Червишевский тракт",
    "Ммс",
    "Центр",
    "Кпд",
    "Зарека",
    "Оборона",
    "Кристалл",
    "Матрешка",
    "Восточка",
    "Солнечный",
    "Колумб",
    "Вояж, цум",
    "Сити молл",
)

_CANONICAL_BY_CASEFOLD: dict[str, str] = {district.casefold(): district for district in DISTRICTS}


def normalize_district(value: str) -> str:
    """Return the canonical district spelling or raise `ValueError`.

    Comparison is case-insensitive and ignores extra whitespace, while the
    stored value is always one of `DISTRICTS`.
    """

    collapsed = " ".join(str(value).split())
    canonical = _CANONICAL_BY_CASEFOLD.get(collapsed.casefold())
    if canonical is None:
        raise ValueError("Неизвестный район. Выберите район из списка.")
    return canonical


def is_valid_district(value: str) -> bool:
    try:
        normalize_district(value)
    except ValueError:
        return False
    return True
