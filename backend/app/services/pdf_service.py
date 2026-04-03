from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

from PIL import Image, ImageOps


MAX_IMAGE_DIMENSION = 2200
WATERMARK_TEMPLATE = "SHARED VIA DOCUSHIELD AI - {date} - FOR VERIFICATION ONLY"


def _prepare_image(image_bytes: bytes) -> tuple[BytesIO, tuple[int, int]]:
    try:
        image = Image.open(BytesIO(image_bytes))
        image = ImageOps.exif_transpose(image)
    except OSError as exc:
        raise ValueError("Failed to decode masked image") from exc

    resampling = getattr(Image, "Resampling", Image)

    if image.mode in {"RGBA", "LA"}:
        background = Image.new("RGB", image.size, "white")
        alpha = image.getchannel("A")
        background.paste(image.convert("RGB"), mask=alpha)
        image = background
    elif image.mode != "RGB":
        image = image.convert("RGB")

    if max(image.size) > MAX_IMAGE_DIMENSION:
        image.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), resampling.LANCZOS)

    encoded = BytesIO()
    image.save(encoded, format="JPEG", quality=85)
    encoded.seek(0)
    return encoded, image.size


async def generate_masked_pdf(
    image_bytes: bytes,
    document_id: str,
    share_token: str,
) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape, portrait
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    timestamp = datetime.now(timezone.utc)
    watermark_text = WATERMARK_TEMPLATE.format(date=timestamp.date().isoformat())
    optimized_image, image_size = _prepare_image(image_bytes)

    page_size = landscape(A4) if image_size[0] >= image_size[1] else portrait(A4)
    page_width, page_height = page_size
    image_width, image_height = image_size
    margin = 24
    scale = min(
        (page_width - (margin * 2)) / image_width,
        (page_height - (margin * 2)) / image_height,
    )
    draw_width = image_width * scale
    draw_height = image_height * scale
    x_pos = (page_width - draw_width) / 2
    y_pos = (page_height - draw_height) / 2

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=page_size)
    pdf.setAuthor("DocuShield AI")
    pdf.setCreator("DocuShield AI")
    pdf.setTitle(f"Masked Document {document_id}")
    pdf.setSubject(
        f"document_id={document_id}; share_token={share_token}; timestamp={timestamp.isoformat()}"
    )
    pdf.setKeywords(f"document_id={document_id},share_token={share_token},timestamp={timestamp.isoformat()}")
    pdf.drawImage(
        ImageReader(optimized_image),
        x_pos,
        y_pos,
        width=draw_width,
        height=draw_height,
        preserveAspectRatio=True,
        mask="auto",
    )

    pdf.saveState()
    pdf.translate(page_width / 2, page_height / 2)
    pdf.rotate(33)
    font_size = min(page_width, page_height) / 11
    while font_size > 16 and pdf.stringWidth(watermark_text, "Helvetica-Bold", font_size) > page_width * 0.84:
        font_size -= 2
    pdf.setFont("Helvetica-Bold", font_size)
    pdf.setFillColor(colors.Color(0.78, 0.78, 0.78))
    pdf.drawCentredString(0, 0, watermark_text)
    pdf.restoreState()

    pdf.showPage()
    pdf.save()
    pdf_bytes = buffer.getvalue()
    if not pdf_bytes:
        raise ValueError("Failed to generate masked PDF")
    return pdf_bytes
