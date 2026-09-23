from __future__ import annotations

import io
import math
from dataclasses import dataclass
from statistics import median

from PIL import Image


@dataclass(frozen=True)
class ImageFeatures:
    phash: str
    mean_rgb: list[int]
    width_px: int
    height_px: int


def _open_image(data: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(data))
    # 对 GIF/TIFF 等多帧图片，Alpha 阶段统一使用首帧。
    try:
        image.seek(0)
    except Exception:
        pass
    return image.convert("RGB")


def _dct_low_frequency(gray_values: list[float], size: int = 32, low: int = 8) -> list[float]:
    """计算 32x32 灰度图的低频 8x8 DCT 系数。

    这里只计算 pHash 需要的低频区，因此无需引入 numpy/scipy，便于 HiAgent
    外部服务的轻量部署。
    """
    if len(gray_values) != size * size:
        raise ValueError("gray_values 尺寸与 size 不匹配")

    cos_table = [
        [math.cos(((2 * x + 1) * u * math.pi) / (2 * size)) for x in range(size)]
        for u in range(low)
    ]
    coeffs: list[float] = []
    for v in range(low):
        cv = math.sqrt(1 / size) if v == 0 else math.sqrt(2 / size)
        for u in range(low):
            cu = math.sqrt(1 / size) if u == 0 else math.sqrt(2 / size)
            total = 0.0
            for y in range(size):
                row_base = y * size
                cy = cos_table[v][y]
                for x in range(size):
                    total += gray_values[row_base + x] * cos_table[u][x] * cy
            coeffs.append(cu * cv * total)
    return coeffs


def perceptual_hash(image: Image.Image, hash_size: int = 8, highfreq_factor: int = 4) -> str:
    sample_size = hash_size * highfreq_factor
    gray = image.convert("L").resize((sample_size, sample_size), Image.Resampling.LANCZOS)
    gray_data = gray.get_flattened_data() if hasattr(gray, "get_flattened_data") else gray.getdata()
    pixels = [float(value) for value in gray_data]
    coeffs = _dct_low_frequency(pixels, size=sample_size, low=hash_size)

    # 标准 pHash 使用除 DC 分量外低频系数的中位数作为二值化阈值。
    threshold = median(coeffs[1:]) if len(coeffs) > 1 else coeffs[0]
    bits = 0
    for coefficient in coeffs:
        bits = (bits << 1) | int(coefficient > threshold)
    hex_len = (hash_size * hash_size + 3) // 4
    return f"{bits:0{hex_len}x}"


def extract_image_features(data: bytes) -> ImageFeatures:
    image = _open_image(data)
    width, height = image.size
    # 缩小后取平均色，降低不同压缩方式带来的噪声。
    sample = image.resize((32, 32), Image.Resampling.BILINEAR)
    sample_data = sample.get_flattened_data() if hasattr(sample, "get_flattened_data") else sample.getdata()
    rgb = list(sample_data)
    count = max(1, len(rgb))
    mean_rgb = [
        round(sum(pixel[channel] for pixel in rgb) / count)
        for channel in range(3)
    ]
    return ImageFeatures(
        phash=perceptual_hash(image),
        mean_rgb=mean_rgb,
        width_px=width,
        height_px=height,
    )


def hamming_distance(hash_a: str, hash_b: str) -> int:
    if not hash_a or not hash_b:
        raise ValueError("pHash 不能为空")
    if len(hash_a) != len(hash_b):
        raise ValueError("pHash 长度不一致")
    return (int(hash_a, 16) ^ int(hash_b, 16)).bit_count()


def color_similarity(rgb_a: list[int] | None, rgb_b: list[int] | None) -> float:
    if not rgb_a or not rgb_b or len(rgb_a) != 3 or len(rgb_b) != 3:
        return 1.0
    distance = math.sqrt(sum((float(a) - float(b)) ** 2 for a, b in zip(rgb_a, rgb_b)))
    max_distance = math.sqrt(3 * (255**2))
    return max(0.0, min(1.0, 1.0 - distance / max_distance))


def aspect_ratio_delta(
    width_a: int | None,
    height_a: int | None,
    width_b: int | None,
    height_b: int | None,
) -> float:
    if not width_a or not height_a or not width_b or not height_b:
        return 0.0
    ratio_a = width_a / height_a
    ratio_b = width_b / height_b
    denominator = max(abs(ratio_a), abs(ratio_b), 1e-9)
    return abs(ratio_a - ratio_b) / denominator
