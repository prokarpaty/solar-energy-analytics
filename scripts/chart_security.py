"""Plain-text security boundaries for chart labels."""

import unicodedata
from html import escape

MAX_LABEL_LENGTH = 256


def plain_label(value):
    """Normalize untrusted chart text."""

    if not isinstance(value, str):
        raise ValueError("Chart label must be a string")

    value = unicodedata.normalize("NFC", value)

    value = "".join(
        " " if unicodedata.category(char) in ("Cc", "Cf")
        else char
        for char in value
    )

    return value[:MAX_LABEL_LENGTH]


def plotly_label(value):
    """Encode plain text for Plotly's HTML-aware labels."""

    return escape(
        plain_label(value),
        quote=True
    )
