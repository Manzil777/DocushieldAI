from PIL import Image, ImageDraw
import os

def add_watermark(image_path, text="For Verification Only"):
    img = Image.open(image_path)
    draw = ImageDraw.Draw(img)

    draw.text((20, 20), text, fill=(255, 0, 0))

    base, ext = os.path.splitext(image_path)
    output_path = f"{base}_watermarked{ext}"
    img.save(output_path)

    return output_path