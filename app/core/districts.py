"""Meeting place: free-form text with a list of suggestions.

The tuple below is only a hint for the client (datalist). Users may type any
meeting place; the server normalizes the value and checks its length instead of
validating it against this list.
"""

from __future__ import annotations

DISTRICT_MIN_LENGTH = 2
DISTRICT_MAX_LENGTH = 40

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


def normalize_district(value: str) -> str:
    """Normalize a free-form meeting place or raise `ValueError`.

    Extra whitespace is collapsed and the value is brought to the same shape as
    the suggestions ("центр", "ЦЕНТР", " центр " → "Центр"), so the catalog
    filter stays case-insensitive and does not create spelling duplicates.
    """

    printable = "".join(char for char in str(value) if char.isprintable())
    collapsed = " ".join(printable.split())
    if not collapsed:
        raise ValueError("Укажите место встречи.")
    if len(collapsed) < DISTRICT_MIN_LENGTH:
        raise ValueError("Место встречи слишком короткое.")
    if len(collapsed) > DISTRICT_MAX_LENGTH:
        raise ValueError(
            f"Место встречи должно быть короче {DISTRICT_MAX_LENGTH} символов."
        )
    return collapsed.lower().capitalize()


def is_valid_district(value: str) -> bool:
    try:
        normalize_district(value)
    except ValueError:
        return False
    return True
