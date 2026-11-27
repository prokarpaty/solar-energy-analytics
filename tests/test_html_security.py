import sys
import tempfile
import unittest
from pathlib import Path
from html.parser import HTMLParser

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT / "scripts"))

from installation_config import load_installation
from render_report import build_context, equipment_rows
from report_sections import apply_sections
from localization import Localizer


PAYLOAD = '<script id="security-test">TEST</script>'
IMAGE = '<img src="https://example.invalid/test" onerror="TEST">'
ATTRIBUTE = '"><svg onload="TEST">'
CSS = '#ffffff; background:url(https://example.invalid/test)'


class DocumentInspector(HTMLParser):

    def __init__(self):
        super().__init__()
        self.tags = []
        self.text_nodes = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.text_nodes.append(data)


class HTMLSecurity(unittest.TestCase):

    def load_profile(self, overrides):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "installation.yaml"
            path.write_text(
                yaml.safe_dump(overrides),
                encoding="utf-8"
            )
            return load_installation(path)

    def render(self, overrides=None, warnings=None,
               language="en", pdf=False,
               timezone="Europe/Kyiv"):

        profile = self.load_profile(overrides or {})

        data = {
            "start": "2026-11-24T00:00:00+02:00",
            "end": "2026-11-25T00:00:00+02:00",
            "generated_at": "2026-11-25T00:10:00+02:00",
            "report_type": "daily",
            "timezone": timezone,
            "energy": {
                "production": {
                    "total": 1.5,
                    "coverage": 100,
                    "status": "complete"
                }
            },
            "measurements": {},
            "configuration_warnings": warnings or []
        }

        context = build_context(
            data, language, profile
        )

        context["profile"] = profile
        context["equipment_rows"] = equipment_rows(
            profile, Localizer(language)
        )
        context["charts"] = []

        apply_sections(context)

        env = Environment(
            loader=FileSystemLoader(
                str(ROOT / "templates")
            ),
            autoescape=select_autoescape(
                ["html", "xml"]
            )
        )

        return env.get_template("report.html").render(
            **context,
            pdf=pdf,
            plotly_js=""
        )

    def assert_safe(self, document, payload):
        self.assertNotIn(payload, document)

        inspector = DocumentInspector()
        inspector.feed(document)
        inspector.close()

        self.assertTrue(
            any(payload in node for node in inspector.text_nodes),
            "Payload was not preserved as literal text"
        )

        for tag, attrs in inspector.tags:
            self.assertNotIn(
                tag, ("script", "svg", "iframe")
            )
            self.assertNotIn("onerror", attrs)
            self.assertNotIn("onload", attrs)
            for attribute in attrs:
                if attribute.startswith("on"):
                    self.assertEqual(
                        (tag, attribute, attrs[attribute]),
                        ("button", "onclick", "window.print()")
                    )
            self.assertNotEqual(
                attrs.get("id"), "security-test"
            )
            self.assertNotIn(
                "example.invalid",
                attrs.get("src", "")
            )

    def test_installation_name(self):
        self.assert_safe(
            self.render({
                "installation": {"name": PAYLOAD}
            }),
            PAYLOAD
        )

    def test_installation_location(self):
        self.assert_safe(
            self.render({
                "installation": {"location": IMAGE}
            }),
            IMAGE
        )

    def test_installation_description(self):
        self.assert_safe(
            self.render({
                "installation": {
                    "description": ATTRIBUTE
                }
            }),
            ATTRIBUTE
        )

    def test_branding_name(self):
        self.assert_safe(
            self.render({
                "branding": {"name": PAYLOAD}
            }),
            PAYLOAD
        )

    def test_equipment_manufacturer(self):
        self.assert_safe(
            self.render({
                "equipment": {
                    "inverter": {
                        "manufacturer": IMAGE
                    }
                }
            }),
            IMAGE
        )

    def test_equipment_model(self):
        self.assert_safe(
            self.render({
                "equipment": {
                    "inverter": {
                        "model": ATTRIBUTE
                    }
                }
            }),
            ATTRIBUTE
        )

    def test_configuration_warning(self):
        self.assert_safe(
            self.render(warnings=[PAYLOAD]),
            PAYLOAD
        )

    def test_timezone_text(self):
        self.assert_safe(
            self.render(timezone=IMAGE),
            IMAGE
        )

    def test_primary_color_injection(self):
        with self.assertRaises(ValueError):
            self.load_profile({
                "branding": {"primary_color": CSS}
            })

    def test_accent_color_injection(self):
        with self.assertRaises(ValueError):
            self.load_profile({
                "branding": {"accent_color": CSS}
            })

    def test_external_logo_rejected(self):
        with self.assertRaises(ValueError):
            self.load_profile({
                "branding": {
                    "logo": "https://example.invalid/logo.png"
                }
            })

    def test_bilingual_rendering(self):
        for language in ("en", "uk"):
            for pdf in (False, True):
                with self.subTest(
                    language=language, pdf=pdf
                ):
                    self.assert_safe(
                        self.render(
                            overrides={
                                "installation": {
                                    "name": PAYLOAD
                                }
                            },
                            language=language,
                            pdf=pdf
                        ),
                        PAYLOAD
                    )


if __name__ == "__main__":
    unittest.main()
