import sys
import unittest
from pathlib import Path
from html import unescape
from html.parser import HTMLParser

import plotly.graph_objects as go

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "scripts")
)

from chart_security import (
    plain_label,
    plotly_label,
    MAX_LABEL_LENGTH
)


class Inspector(HTMLParser):

    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class ChartSecurity(unittest.TestCase):

    def test_english(self):
        self.assertEqual(
            plain_label("Office & Garage"),
            "Office & Garage"
        )

    def test_ukrainian(self):
        self.assertEqual(
            plotly_label("Офіс та гараж"),
            "Офіс та гараж"
        )

    def test_ampersand(self):
        self.assertEqual(
            plotly_label("Office & Garage"),
            "Office &amp; Garage"
        )

    def test_script(self):
        value = '<script>TEST</script>'
        self.assertNotIn("<", plotly_label(value))
        self.assertEqual(
            unescape(plotly_label(value)),
            value
        )

    def test_image_handler(self):
        value = '<img src="x" onerror="TEST">'
        self.assertNotIn("<img", plotly_label(value))
        self.assertEqual(
            unescape(plotly_label(value)),
            value
        )

    def test_svg_handler(self):
        value = '<svg onload="TEST">'
        self.assertNotIn("<svg", plotly_label(value))

    def test_javascript_link(self):
        value = '<a href="javascript:void(0)">TEST</a>'
        self.assertNotIn("<a", plotly_label(value))

    def test_existing_entities(self):
        value = "&lt;script&gt;"
        self.assertEqual(
            unescape(plotly_label(value)),
            value
        )

    def test_control_characters(self):
        self.assertEqual(
            plain_label("Office\x00\x1b\nGarage"),
            "Office   Garage"
        )

    def test_bidi_control(self):
        self.assertEqual(
            plain_label("Office\u202eGarage"),
            "Office Garage"
        )

    def test_unicode_normalization(self):
        self.assertEqual(
            plain_label("e\u0301"),
            "é"
        )

    def test_length_limit(self):
        self.assertEqual(
            len(plain_label("A" * 10000)),
            MAX_LABEL_LENGTH
        )

    def test_invalid_types(self):
        for value in (None, 123, [], {}, True):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    plain_label(value)

    def test_matplotlib_plain_text(self):
        value = "Офіс & гараж <TEST>"
        self.assertEqual(plain_label(value), value)

    def test_plotly_serialization(self):
        payload = (
            '</script><script id="security-test">'
            'TEST</script>'
        )

        fig = go.Figure(
            go.Scatter(
                x=[1, 2],
                y=[3, 4],
                name=plotly_label(payload)
            )
        )

        fig.update_layout(
            title_text=plotly_label(payload)
        )

        document = fig.to_html(
            full_html=False,
            include_plotlyjs=False
        )

        inspector = Inspector()
        inspector.feed(document)
        inspector.close()

        scripts = [
            attrs for tag, attrs in inspector.tags
            if tag == "script"
        ]

        self.assertEqual(len(scripts), 1)
        self.assertNotIn(payload, document)

        for tag, attrs in inspector.tags:
            self.assertNotEqual(
                attrs.get("id"),
                "security-test"
            )

            for attribute in attrs:
                self.assertFalse(
                    attribute.startswith("on")
                )


if __name__ == "__main__":
    unittest.main()
