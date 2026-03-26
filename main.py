from flask import Flask, render_template, request, send_from_directory
import os
import uuid
import time

from utils.ocr import extract_text
from utils.detection import detect_sensitive
from utils.masking import mask_aadhaar, mask_pan
from utils.image_masking import mask_aadhaar_in_image
from utils.face_verify import verify_faces
from utils.watermark import add_watermark

app = Flask(__name__)
UPLOAD_FOLDER = "uploads"

# 🔐 Storage for links
shared_links = {}
EXPIRY_TIME = 600  # 10 minutes


@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        file = request.files["file"]
        selfie = request.files["selfie"]

        if file and selfie:
            path = os.path.join(UPLOAD_FOLDER, file.filename)
            file.save(path)

            selfie_path = os.path.join(UPLOAD_FOLDER, selfie.filename)
            selfie.save(selfie_path)

            # OCR
            text = extract_text(path)

            # Detect sensitive data
            detected = detect_sensitive(text)

            # Mask text
            masked_text = text
            for num in detected["aadhaar"]:
                masked_text = masked_text.replace(num, mask_aadhaar(num))
            for pan in detected["pan"]:
                masked_text = masked_text.replace(pan, mask_pan(pan))

            # Mask image
            masked_img = mask_aadhaar_in_image(path)

            # Add watermark
            final_img = add_watermark(masked_img)

            # Face verification
            face_match = verify_faces(path, selfie_path)

            filename = os.path.basename(final_img)

            # 🔗 Generate secure link
            link_id = str(uuid.uuid4())

            shared_links[link_id] = {
                "file": filename,
                "time": time.time()
            }

            share_link = f"http://127.0.0.1:5000/view/{link_id}"

            return render_template(
                "result.html",
                original=text,
                masked=masked_text,
                masked_image=filename,
                face_match=face_match,
                share_link=share_link
            )

    return render_template("index.html")


# Serve uploaded files
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


# 🔐 Secure view route
@app.route('/view/<link_id>')
def view_file(link_id):
    data = shared_links.get(link_id)

    if not data:
        return "<h2>❌ Invalid Link</h2>"

    # Check expiry
    if time.time() - data["time"] > EXPIRY_TIME:
        return "<h2>⏳ Link Expired</h2>"

    return f"""
    <html>
    <head>
        <title>Secure View</title>
        <style>
            body {{
                background: #0f2027;
                color: white;
                text-align: center;
                font-family: Arial;
                padding: 50px;
            }}
            img {{
                width: 400px;
                border-radius: 10px;
                margin-top: 20px;
            }}
        </style>
    </head>
    <body>
        <h2>🔐 Secure Document View</h2>
        <p>⚠️ This document is watermarked and time-restricted</p>
        <img src="/uploads/{data['file']}">
        <p>⏳ This link will expire soon</p>
    </body>
    </html>
    """


if __name__ == "__main__":
    app.run(debug=True)