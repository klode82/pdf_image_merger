"""
pdf_builder.py
--------------
Pure image/PDF logic for PDFImageMerger. No GUI, no pywebview here on purpose:
this module is fully unit-testable on its own and is the only place that
knows how images get turned into PDF pages.
"""

from __future__ import annotations

import io
import os
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image, ImageOps

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp", ".gif"}

# Physical page sizes in millimeters (portrait, width x height)
PAGE_SIZES_MM = {
    "A4": (210.0, 297.0),
    "A5": (148.0, 210.0),
    "Letter": (215.9, 279.4),
    "Legal": (215.9, 355.6),
}

# "auto" is a page format handled separately: each page matches its own image.
AUTO_FORMAT = "auto"

QUALITY_PRESETS = {"low": 55, "medium": 80, "high": 95}

# Rough per-document / per-page PDF structural overhead used by the estimator
# (xref table, object headers, trailer...). Deliberately small and conservative.
PDF_FIXED_OVERHEAD_BYTES = 2_048
PDF_PER_PAGE_OVERHEAD_BYTES = 900

# How many images to actually render when estimating size for a big batch.
ESTIMATE_SAMPLE_CAP = 8

WHITE = (255, 255, 255)


@dataclass
class ImageInfo:
    path: str
    name: str
    size_bytes: int
    width: int
    height: int
    ext: str

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "name": self.name,
            "size_bytes": self.size_bytes,
            "size_human": human_size(self.size_bytes),
            "width": self.width,
            "height": self.height,
            "ext": self.ext,
        }


# ---------------------------------------------------------------------------
# Discovery / inspection
# ---------------------------------------------------------------------------

def is_supported_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS


def list_images(folder: Path) -> list[Path]:
    """Non-recursive: every supported image directly inside `folder`, sorted by name."""
    folder = Path(folder)
    if not folder.is_dir():
        return []
    return sorted(
        (p for p in folder.iterdir() if is_supported_image(p)),
        key=lambda p: p.name.lower(),
    )


def expand_dropped_path(path: Path) -> list[Path]:
    """A dropped item can be a single image or a folder full of them."""
    path = Path(path)
    if path.is_dir():
        return list_images(path)
    if is_supported_image(path):
        return [path]
    return []


def get_image_info(path: Path) -> ImageInfo | None:
    path = Path(path)
    try:
        with Image.open(path) as img:
            width, height = img.size
        size_bytes = path.stat().st_size
    except Exception:
        return None
    return ImageInfo(
        path=str(path),
        name=path.name,
        size_bytes=size_bytes,
        width=width,
        height=height,
        ext=path.suffix.lower(),
    )


def make_thumbnail_data_uri(path: Path, max_side: int = 96) -> str | None:
    """Small base64 JPEG data URI used for the file-list preview. Best-effort."""
    try:
        with Image.open(path) as img:
            img = ImageOps.exif_transpose(img)
            img = _to_rgb(img)
            img.thumbnail((max_side, max_side), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=70)
            import base64

            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            return f"data:image/jpeg;base64,{b64}"
    except Exception:
        return None


def human_size(num_bytes: float) -> str:
    step = 1024.0
    for unit in ("B", "KB", "MB", "GB"):
        if abs(num_bytes) < step:
            return f"{num_bytes:.0f} {unit}" if unit == "B" else f"{num_bytes:.1f} {unit}"
        num_bytes /= step
    return f"{num_bytes:.1f} TB"


# ---------------------------------------------------------------------------
# Page geometry
# ---------------------------------------------------------------------------

def mm_to_px(mm: float, dpi: int) -> int:
    return max(1, round(mm / 25.4 * dpi))


def compute_page_size_px(page_format: str, orientation: str, dpi: int) -> tuple[int, int] | None:
    """Returns (width_px, height_px) for a fixed page format, or None for 'auto'."""
    if page_format == AUTO_FORMAT:
        return None
    w_mm, h_mm = PAGE_SIZES_MM[page_format]
    w_px, h_px = mm_to_px(w_mm, dpi), mm_to_px(h_mm, dpi)
    if orientation == "landscape" and w_px < h_px:
        w_px, h_px = h_px, w_px
    elif orientation == "portrait" and w_px > h_px:
        w_px, h_px = h_px, w_px
    return w_px, h_px


def _to_rgb(img: Image.Image) -> Image.Image:
    """Flatten transparency onto white and normalize to plain RGB."""
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, WHITE)
        bg.paste(rgba, mask=rgba.split()[-1])
        return bg
    if img.mode != "RGB":
        return img.convert("RGB")
    return img


def _fit_contain(img: Image.Image, target_size: tuple[int, int]) -> Image.Image:
    """Scale `img` to fit inside target_size preserving aspect ratio, centered on white."""
    target_w, target_h = target_size
    src_w, src_h = img.size
    scale = min(target_w / src_w, target_h / src_h)
    new_w = max(1, round(src_w * scale))
    new_h = max(1, round(src_h * scale))
    resized = img.resize((new_w, new_h), Image.LANCZOS)
    canvas = Image.new("RGB", target_size, WHITE)
    canvas.paste(resized, ((target_w - new_w) // 2, (target_h - new_h) // 2))
    return canvas


def render_page(path: Path, page_size_px: tuple[int, int] | None) -> Image.Image:
    """Open one source image and turn it into a single ready-to-save RGB PDF page."""
    with Image.open(path) as raw:
        img = ImageOps.exif_transpose(raw)
        img = _to_rgb(img)
        if page_size_px is None:
            return img.copy()
        return _fit_contain(img, page_size_px)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def _quality_from_settings(settings: dict) -> int:
    quality = settings.get("quality", "medium")
    if isinstance(quality, int):
        return max(1, min(95, quality))
    return QUALITY_PRESETS.get(quality, QUALITY_PRESETS["medium"])


def _is_original_quality(settings: dict) -> bool:
    """"Take the images as they are": no resizing to a page format and no
    lossy recompression, at the cost of a much larger file."""
    return bool(settings.get("original_quality", False))


def _page_size_from_settings(settings: dict) -> tuple[int, int] | None:
    if _is_original_quality(settings):
        return None
    page_format = settings.get("page_format", AUTO_FORMAT)
    orientation = settings.get("orientation", "portrait")
    dpi = int(settings.get("dpi", 150))
    return compute_page_size_px(page_format, orientation, dpi)


# ---------------------------------------------------------------------------
# Size estimation
# ---------------------------------------------------------------------------

def estimate_pdf_size(image_paths: list[Path], settings: dict) -> dict:
    """
    Renders a representative sample of pages (real resize + real JPEG encode)
    and extrapolates. Close to the real output because the sampled encode
    uses the exact same code path build_pdf() uses.
    """
    image_paths = [Path(p) for p in image_paths]
    total = len(image_paths)
    if total == 0:
        return {"estimated_bytes": 0, "estimated_human": human_size(0), "sampled": 0, "total": 0}

    page_size_px = _page_size_from_settings(settings)
    quality = _quality_from_settings(settings)
    original_quality = _is_original_quality(settings)

    if total <= ESTIMATE_SAMPLE_CAP:
        sample_indexes = list(range(total))
    else:
        # Evenly spaced sample across the whole list, so it reflects varied content.
        step = total / ESTIMATE_SAMPLE_CAP
        sample_indexes = sorted({int(i * step) for i in range(ESTIMATE_SAMPLE_CAP)})

    sample_bytes = []
    for idx in sample_indexes:
        try:
            if original_quality:
                # Mirrors build_pdf()/_append_original_page() exactly: a
                # passthrough-eligible JPEG costs its own file size (it's
                # embedded untouched), anything else costs its lossless
                # Flate-compressed size.
                passthrough = _try_jpeg_passthrough(image_paths[idx])
                if passthrough is not None:
                    sample_bytes.append(len(passthrough[0]))
                else:
                    page = render_page(image_paths[idx], page_size_px)
                    sample_bytes.append(len(zlib.compress(page.tobytes(), level=6)))
            else:
                page = render_page(image_paths[idx], page_size_px)
                buf = io.BytesIO()
                page.save(buf, format="JPEG", quality=quality)
                sample_bytes.append(len(buf.getvalue()))
        except Exception:
            continue

    if not sample_bytes:
        return {"estimated_bytes": 0, "estimated_human": human_size(0), "sampled": 0, "total": total}

    avg_bytes_per_page = sum(sample_bytes) / len(sample_bytes)
    estimated = (
        avg_bytes_per_page * total
        + PDF_PER_PAGE_OVERHEAD_BYTES * total
        + PDF_FIXED_OVERHEAD_BYTES
    )
    return {
        "estimated_bytes": round(estimated),
        "estimated_human": human_size(estimated),
        "sampled": len(sample_bytes),
        "total": total,
        "is_partial_sample": len(sample_bytes) < total,
    }


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


# Pillow's own PDF writer needs every page's *decoded* pixels resident in
# memory at once (its save_all/append_images path fully materializes them
# before writing anything) — fine for a handful of images, but a batch of
# hundreds at print resolution can be gigabytes. We cap how many decoded
# pages exist at once by building the PDF in small chunks and stitching the
# chunks together with pikepdf, which only has to hold each page's already-
# compressed JPEG stream, not raw pixels.
TARGET_CHUNK_MEMORY_BYTES = 250 * 1024 * 1024  # ~250MB of raw pixels per chunk
MIN_CHUNK_SIZE = 1
MAX_CHUNK_SIZE = 50


def _estimate_chunk_size(image_paths: list[Path], page_size_px: tuple[int, int] | None) -> int:
    if page_size_px is not None:
        width, height = page_size_px
    else:
        try:
            with Image.open(image_paths[0]) as probe:
                width, height = probe.size
        except Exception:
            width, height = 2000, 2000  # conservative guess if the first image can't be read
    bytes_per_page = max(1, width * height * 3)  # decoded RGB, worst case before JPEG encoding
    size = TARGET_CHUNK_MEMORY_BYTES // bytes_per_page
    return max(MIN_CHUNK_SIZE, min(MAX_CHUNK_SIZE, size))


def _render_chunk_to_pdf_bytes(paths: list[Path], page_size_px, dpi: int, quality: int) -> bytes:
    pages = [render_page(p, page_size_px) for p in paths]
    try:
        buf = io.BytesIO()
        first, rest = pages[0], pages[1:]
        first.save(buf, "PDF", save_all=True, append_images=rest, resolution=float(dpi), quality=quality)
        return buf.getvalue()
    finally:
        for p in pages:
            p.close()


_JPEG_EXTENSIONS = {".jpg", ".jpeg"}

# EXIF orientation tag -> (content-stream cm matrix in pixel units, page
# (width, height) in pixel units). Only the four *pure rotation* tags are
# covered — the four mirrored ones (2/4/5/7) essentially never come out of a
# real camera, and getting a mirror matrix wrong is a much worse failure mode
# than just falling back to the always-correct re-encode path for them.
# Empirically derived and checked against a real render (Ghostscript/Poppler)
# of an asymmetric 4-quadrant test image against PIL's own
# ImageOps.exif_transpose as ground truth — see the project's dev notes.
_PASSTHROUGH_ORIENTATION_MATRIX = {
    1: lambda w, h: ((w, 0, 0, h, 0, 0), (w, h)),
    3: lambda w, h: ((-w, 0, 0, -h, w, h), (w, h)),
    6: lambda w, h: ((0, -w, h, 0, 0, w), (h, w)),
    8: lambda w, h: ((0, w, -h, 0, h, 0), (h, w)),
}


def _try_jpeg_passthrough(path: Path):
    """If `path` is a plain baseline JPEG in a mode/orientation we can embed
    byte-for-byte, return (raw_bytes, color_space_name, matrix_px,
    page_size_px). Otherwise None, so the caller falls back to decoding it.
    """
    if path.suffix.lower() not in _JPEG_EXTENSIONS:
        return None
    try:
        with Image.open(path) as img:
            if img.mode not in ("RGB", "L"):
                return None  # CMYK JPEGs etc. — not worth the extra risk here
            mode = img.mode
            width, height = img.size
            orientation = img.getexif().get(0x0112, 1)
        geometry = _PASSTHROUGH_ORIENTATION_MATRIX.get(orientation)
        if geometry is None:
            return None  # mirrored (2/4/5/7) or unrecognized tag
        matrix_px, page_size_px = geometry(width, height)
        raw_bytes = path.read_bytes()
    except Exception:
        return None
    return raw_bytes, mode, matrix_px, page_size_px


def _append_original_page(pdf, path: Path, dpi: int) -> None:
    """Add one page holding `path` exactly as it is.

    Pillow's own PDF writer always re-encodes RGB images as JPEG — there is
    no "just don't recompress" flag to reach for (confirmed by reading
    PdfImagePlugin: the DCTDecode branch is unconditional for mode "RGB").
    So "original quality" builds pages by hand instead. Two cases:

    - Plain JPEG, non-mirrored orientation: embed the file's *own bytes*
      untouched as a DCTDecode stream — genuinely the original file, byte for
      byte, not a re-encode of it. The only thing we add is a placement
      matrix in the page's content stream to compensate for EXIF rotation
      (PDF viewers don't look at JPEG EXIF tags themselves).
    - Anything else (PNG/BMP/TIFF/WEBP/GIF, or a JPEG mode/orientation we
      don't special-case): decode once, keep every pixel value exactly as
      decoded, and store it as a Flate (zlib, lossless) image XObject.
    """
    import pikepdf
    from pikepdf import Dictionary, Name, Stream

    passthrough = _try_jpeg_passthrough(path)
    if passthrough is not None:
        raw_bytes, mode, (a, b, c, d, e, f), (page_w_px, page_h_px) = passthrough
        image_xobj = Stream(pdf, raw_bytes)
        image_xobj.Type = Name.XObject
        image_xobj.Subtype = Name.Image
        with Image.open(path) as probe:
            image_xobj.Width, image_xobj.Height = probe.size
        image_xobj.BitsPerComponent = 8
        image_xobj.ColorSpace = Name.DeviceGray if mode == "L" else Name.DeviceRGB
        image_xobj.Filter = Name.DCTDecode

        scale = 72.0 / dpi
        page_w_pt, page_h_pt = page_w_px * scale, page_h_px * scale
        a, b, c, d, e, f = (v * scale for v in (a, b, c, d, e, f))
    else:
        img = render_page(path, None)  # None => keep the image's own pixel size
        try:
            width, height = img.size
            compressed = zlib.compress(img.tobytes(), level=6)
        finally:
            img.close()

        image_xobj = Stream(pdf, compressed)
        image_xobj.Type = Name.XObject
        image_xobj.Subtype = Name.Image
        image_xobj.Width = width
        image_xobj.Height = height
        image_xobj.BitsPerComponent = 8
        image_xobj.ColorSpace = Name.DeviceRGB
        image_xobj.Filter = Name.FlateDecode

        page_w_pt = width * 72.0 / dpi
        page_h_pt = height * 72.0 / dpi
        a, b, c, d, e, f = page_w_pt, 0, 0, page_h_pt, 0, 0

    content = f"q {a:.4f} {b:.4f} {c:.4f} {d:.4f} {e:.4f} {f:.4f} cm /Im0 Do Q".encode("ascii")
    pdf.pages.append(
        pikepdf.Page(
            Dictionary(
                Type=Name.Page,
                MediaBox=[0, 0, page_w_pt, page_h_pt],
                Resources=Dictionary(XObject=Dictionary(Im0=image_xobj)),
                Contents=Stream(pdf, content),
            )
        )
    )


def build_pdf(
    image_paths: list[Path],
    output_path: Path,
    settings: dict,
    progress_cb: Callable[[int, int], None] | None = None,
) -> dict:
    import pikepdf

    image_paths = [Path(p) for p in image_paths]
    if not image_paths:
        raise ValueError("Nessuna immagine da unire.")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    original_quality = _is_original_quality(settings)
    dpi = int(settings.get("dpi", 150))
    total = len(image_paths)

    merged = pikepdf.Pdf.new()
    try:
        if original_quality:
            # No Pillow batch save here, so no "hold everything decoded at
            # once" constraint either — one image is ever decoded at a time,
            # so this scales to large batches without any chunking.
            for i, path in enumerate(image_paths):
                _append_original_page(merged, path, dpi)
                if progress_cb:
                    progress_cb(i + 1, total)
        else:
            page_size_px = _page_size_from_settings(settings)
            quality = _quality_from_settings(settings)
            chunk_size = _estimate_chunk_size(image_paths, page_size_px)
            done = 0
            for start in range(0, total, chunk_size):
                chunk_paths = image_paths[start : start + chunk_size]
                chunk_pdf_bytes = _render_chunk_to_pdf_bytes(chunk_paths, page_size_px, dpi, quality)
                with pikepdf.Pdf.open(io.BytesIO(chunk_pdf_bytes)) as chunk_pdf:
                    merged.pages.extend(chunk_pdf.pages)
                done += len(chunk_paths)
                if progress_cb:
                    progress_cb(done, total)
        merged.save(output_path)
    finally:
        merged.close()

    return {
        "output_path": str(output_path),
        "pages": total,
        "size_bytes": os.path.getsize(output_path),
        "size_human": human_size(os.path.getsize(output_path)),
    }
