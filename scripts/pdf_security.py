"""Restricted resource loading for self-contained PDF reports."""

import base64
import binascii
import io

from PIL import Image

from weasyprint.urls import (
    URLFetcher,
    URLFetcherResponse,
    FatalURLFetchingError,
)

PNG_PREFIX = "data:image/png;base64,"

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000
MAX_IMAGE_DIMENSION = 8192

MAX_ENCODED_LENGTH = (
    4 * ((MAX_IMAGE_BYTES + 2) // 3)
)


def decode_png(url):
    """Validate and decode an approved embedded PNG resource."""

    if not isinstance(url, str):
        raise FatalURLFetchingError(
            "Invalid PDF resource"
        )

    if not url.startswith(PNG_PREFIX):
        raise FatalURLFetchingError(
            "PDF resource type prohibited"
        )

    encoded = url[len(PNG_PREFIX):]

    if not encoded or len(encoded) > MAX_ENCODED_LENGTH:
        raise FatalURLFetchingError(
            "PDF image size prohibited"
        )

    try:
        raw = base64.b64decode(
            encoded,
            validate=True
        )
    except (ValueError, binascii.Error):
        raise FatalURLFetchingError(
            "Invalid PDF image encoding"
        ) from None

    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise FatalURLFetchingError(
            "PDF image size prohibited"
        )

    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise FatalURLFetchingError(
            "Invalid PDF image format"
        )

    try:
        with Image.open(io.BytesIO(raw)) as image:

            if image.format != "PNG":
                raise ValueError()

            width, height = image.size

            if (
                width < 1
                or height < 1
                or width > MAX_IMAGE_DIMENSION
                or height > MAX_IMAGE_DIMENSION
                or width * height > MAX_IMAGE_PIXELS
            ):
                raise ValueError()

            if getattr(image, "is_animated", False):
                raise ValueError()

            image.verify()

        with Image.open(io.BytesIO(raw)) as image:
            image.load()

    except Exception:
        raise FatalURLFetchingError(
            "Invalid or prohibited PDF image"
        ) from None

    return raw


class RestrictedPDFFetcher(URLFetcher):
    """Allow only validated embedded PNG images."""

    def fetch(self, url, *args, **kwargs):

        raw = decode_png(url)

        return URLFetcherResponse(
            url=url,
            body=raw,
            headers={
                "Content-Type": "image/png",
                "Content-Length": str(len(raw)),
            },
            status=200,
        )
