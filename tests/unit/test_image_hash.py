from io import BytesIO

from PIL import Image, ImageDraw

from bid_compare_agent.utils.image import extract_image_features, hamming_distance


def _png(size: int) -> bytes:
    image = Image.new("RGB", (size, size), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((size // 8, size // 8, size * 7 // 8, size * 7 // 8), outline="black", width=max(1, size // 16))
    draw.line((0, 0, size - 1, size - 1), fill="blue", width=max(1, size // 16))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_phash_is_stable_across_resize():
    small = extract_image_features(_png(64))
    large = extract_image_features(_png(128))
    assert hamming_distance(small.phash, large.phash) <= 15
