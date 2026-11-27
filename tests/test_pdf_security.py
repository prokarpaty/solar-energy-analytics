import sys
import io
import base64
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from weasyprint import HTML
from weasyprint.urls import FatalURLFetchingError

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "scripts")
)

from pdf_security import (
    decode_png,
    RestrictedPDFFetcher,
    PNG_PREFIX,
    MAX_ENCODED_LENGTH,
    MAX_IMAGE_DIMENSION,
)


def make_png(width=100, height=100):
    buffer = io.BytesIO()

    Image.new(
        "RGB",
        (width, height),
        "blue"
    ).save(buffer, format="PNG")

    return buffer.getvalue()


def data_url(raw):
    return PNG_PREFIX + base64.b64encode(raw).decode("ascii")


class PDFSecurity(unittest.TestCase):

    def test_valid_png(self):
        raw = make_png()
        self.assertEqual(decode_png(data_url(raw)), raw)

    def test_http(self):
        with self.assertRaises(FatalURLFetchingError):
            decode_png("http://example.invalid/test.png")

    def test_https(self):
        with self.assertRaises(FatalURLFetchingError):
            decode_png("https://example.invalid/test.png")

    def test_local_file(self):
        with self.assertRaises(FatalURLFetchingError):
            decode_png("file:///tmp/security-test.png")

    def test_ftp(self):
        with self.assertRaises(FatalURLFetchingError):
            decode_png("ftp://example.invalid/test.png")

    def test_relative_path(self):
        with self.assertRaises(FatalURLFetchingError):
            decode_png("../../security-test.png")

    def test_svg(self):
        with self.assertRaises(FatalURLFetchingError):
            decode_png("data:image/svg+xml;base64,AAAA")

    def test_html(self):
        with self.assertRaises(FatalURLFetchingError):
            decode_png("data:text/html;base64,AAAA")

    def test_invalid_base64(self):
        with self.assertRaises(FatalURLFetchingError):
            decode_png(PNG_PREFIX + "!!!")

    def test_empty_image(self):
        with self.assertRaises(FatalURLFetchingError):
            decode_png(PNG_PREFIX)

    def test_invalid_png(self):
        with self.assertRaises(FatalURLFetchingError):
            decode_png(data_url(b"NOT A PNG"))

    def test_truncated_png(self):
        with self.assertRaises(FatalURLFetchingError):
            decode_png(data_url(make_png()[:30]))

    def test_invalid_types(self):
        for value in (None, 123, [], {}, b"PNG"):
            with self.subTest(value=value):
                with self.assertRaises(FatalURLFetchingError):
                    decode_png(value)

    def test_encoded_size_limit(self):
        with self.assertRaises(FatalURLFetchingError):
            decode_png(
                PNG_PREFIX + "A" * (MAX_ENCODED_LENGTH + 1)
            )

    def test_decoded_size_limit(self):
        raw = make_png()
        url = data_url(raw)

        with patch(
            "pdf_security.MAX_IMAGE_BYTES",
            len(raw) - 1
        ):
            with self.assertRaises(FatalURLFetchingError):
                decode_png(url)

    def test_dimension_limit(self):
        raw = make_png(MAX_IMAGE_DIMENSION + 1, 1)

        with self.assertRaises(FatalURLFetchingError):
            decode_png(data_url(raw))

    def test_pixel_limit(self):
        raw = make_png(100, 100)

        with patch("pdf_security.MAX_IMAGE_PIXELS", 9999):
            with self.assertRaises(FatalURLFetchingError):
                decode_png(data_url(raw))

    def test_animated_png(self):
        buffer = io.BytesIO()

        first = Image.new("RGB", (10, 10), "red")
        second = Image.new("RGB", (10, 10), "blue")

        first.save(
            buffer,
            format="PNG",
            save_all=True,
            append_images=[second],
            duration=100,
            loop=0
        )

        with self.assertRaises(FatalURLFetchingError):
            decode_png(data_url(buffer.getvalue()))

    def test_fetcher_no_default_delegation(self):
        with patch(
            "weasyprint.urls.URLFetcher.fetch",
            side_effect=AssertionError("Unexpected delegation")
        ) as parent:

            fetcher = RestrictedPDFFetcher()

            fetcher.fetch(data_url(make_png()))

            with self.assertRaises(FatalURLFetchingError):
                fetcher.fetch(
                    "https://example.invalid/test.png"
                )

            parent.assert_not_called()

    def test_actual_pdf_generation(self):
        url = data_url(make_png())

        document = HTML(
            string=f'<img src="{url}">',
            url_fetcher=RestrictedPDFFetcher()
        ).write_pdf()

        self.assertTrue(document.startswith(b"%PDF-"))

    def test_actual_http_rejection(self):
        with self.assertRaises(FatalURLFetchingError):
            HTML(
                string='<img src="http://example.invalid/test.png">',
                url_fetcher=RestrictedPDFFetcher()
            ).write_pdf()

    def test_actual_file_rejection(self):
        with self.assertRaises(FatalURLFetchingError):
            HTML(
                string='<img src="file:///tmp/security-test.png">',
                url_fetcher=RestrictedPDFFetcher()
            ).write_pdf()

    def test_actual_css_import_rejection(self):
        with self.assertRaises(FatalURLFetchingError):
            HTML(
                string=(
                    '<style>@import url('
                    '"https://example.invalid/test.css");'
                    '</style><p>TEST</p>'
                ),
                url_fetcher=RestrictedPDFFetcher()
            ).write_pdf()

    def test_actual_css_background_rejection(self):
        with self.assertRaises(FatalURLFetchingError):
            HTML(
                string=(
                    '<div style="width:100px;height:100px;'
                    "background-image:url('"
                    "https://example.invalid/test.png"
                    "')\">TEST</div>"
                ),
                url_fetcher=RestrictedPDFFetcher()
            ).write_pdf()

    def test_actual_svg_rejection(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"/>'

        url = (
            "data:image/svg+xml;base64,"
            + base64.b64encode(svg).decode("ascii")
        )

        with self.assertRaises(FatalURLFetchingError):
            HTML(
                string=f'<img src="{url}">',
                url_fetcher=RestrictedPDFFetcher()
            ).write_pdf()


if __name__ == "__main__":
    unittest.main()
