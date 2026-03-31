import os, uuid, time
from datetime import datetime
from flask import Flask, render_template, request, send_from_directory, redirect, url_for
import qrcode
from werkzeug.utils import secure_filename

try:
    from utils.ocr import extract_text
    from utils.detection import detect_sensitive
    from utils.masking import mask_aadhaar, mask_pan
    from utils.image_masking import mask_aadhaar_in_image
    from utils.face_verify import verify_faces
    from utils.watermark import add_watermark
except ImportError:
    pass

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
VAULT_FOLDER = os.path.join(BASE_DIR, "vault", "default_user")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(VAULT_FOLDER, exist_ok=True)

shared_links = {}
EXPIRY_TIME = 600 # 10 minutes Expiry Rule

@app.route("/")
def landing():
    return render_template("index.html")

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")

@app.route("/upload/<purpose>", methods=["GET", "POST"])
def upload_page(purpose):
    if request.method == "POST":
        files = request.files.getlist("file")
        if not files or files[0].filename == '':
            return "No file uploaded", 400

        selfie = request.files.get("selfie")
        processed_files = []
        face_match = None
        
        for file in files:
            fname = secure_filename(file.filename)
            unique_fname = str(uuid.uuid4()) + "_" + fname
            
            # --- VAULT MODE: Strict Original Storage ---
            if purpose == 'vault':
                path = os.path.join(VAULT_FOLDER, unique_fname)
                file.save(path)
                continue # Bypasses all visual modifications natively
                
            # --- OTHER MODES: Execute AI Pipeline ---
            path = os.path.join(UPLOAD_FOLDER, unique_fname)
            file.save(path)
            
            text = extract_text(path)
            detected = detect_sensitive(text) if text else {}
            masked_text = text
            current_img_path = path

            # 1. Masking Logistics
            if purpose in ['hotel', 'sharing', 'qr'] and text:
                for num in detected.get("aadhaar", []):
                    masked_text = masked_text.replace(num, mask_aadhaar(num))
                for pan in detected.get("pan", []):
                    masked_text = masked_text.replace(pan, mask_pan(pan))
                current_img_path = mask_aadhaar_in_image(path)
            
            # 2. Watermarking Engine
            if purpose == 'printing':
                watermark_text = "For Printing Only"
            elif purpose == 'hotel':
                watermark_text = "For Hotel Verification Only"
            elif purpose == 'verification':
                watermark_text = "Verified Identity"
            elif purpose in ['sharing', 'qr']:
                watermark_text = "Shared Securely"
            else:
                watermark_text = "Protected Asset"

            final_img = add_watermark(current_img_path, text=watermark_text)
            
            processed_files.append({
                "original": text,
                "masked": masked_text,
                "filename": os.path.basename(final_img)
            })
            
            # 3. Biometric DeepFace Hook
            if purpose == 'verification' and selfie and face_match is None:
                sname = str(uuid.uuid4()) + "_" + secure_filename(selfie.filename)
                spath = os.path.join(UPLOAD_FOLDER, sname)
                selfie.save(spath)
                face_match = verify_faces(path, spath)

        # Handle Routing For Vault
        if purpose == 'vault':
            return redirect(url_for('my_vault'))

        link_id = str(uuid.uuid4())
        shared_links[link_id] = {
            "files": [f["filename"] for f in processed_files],
            "purpose": purpose,
            "time": time.time()
        }

        # Generates Dedicated Secure Expiring Path
        share_link = f"/view/{link_id}"
        full_share_url = request.host_url.rstrip('/') + share_link
        
        # Deploy strict QR code asset generator
        qr = qrcode.make(full_share_url)
        qr_filename = f"qr_{link_id}.png"
        qr.save(os.path.join(UPLOAD_FOLDER, qr_filename))

        return render_template(
            "result.html",
            purpose=purpose,
            processed_files=processed_files,
            face_match=face_match,
            share_link=full_share_url,
            qr_image=qr_filename
        )

    return render_template("upload.html", purpose=purpose)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route('/vault_files/<filename>')
def vault_file(filename):
    return send_from_directory(VAULT_FOLDER, filename, as_attachment=True)

@app.route('/my-vault')
def my_vault():
    files_data = []
    if os.path.exists(VAULT_FOLDER):
        for f in os.listdir(VAULT_FOLDER):
            fpath = os.path.join(VAULT_FOLDER, f)
            if os.path.isfile(fpath):
                stat = os.stat(fpath)
                upload_date = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                files_data.append({
                    "name": f,
                    "date": upload_date,
                    "size": round(stat.st_size / 1024, 2)
                })
    files_data.sort(key=lambda x: x['date'], reverse=True)
    return render_template("vault.html", vault_files=files_data)

@app.route('/view/<link_id>')
def view_file(link_id):
    data = shared_links.get(link_id)

    if not data:
        return render_template("view_dashboard.html", error="❌ Invalid or Missing Encrypted Link")

    purpose = data.get("purpose", "document")
    elapsed = time.time() - data["time"]

    if elapsed > EXPIRY_TIME:
        return render_template("view_dashboard.html", error="⏳ Secure Link has Expired (Destructed after 10 mins)")

    files_to_show = data.get("files", [])

    return render_template(
        "view_dashboard.html",
        files=files_to_show,
        purpose=purpose,
        time_left=int(EXPIRY_TIME - elapsed),
        error=None
    )

if __name__ == "__main__":
    app.run(debug=True)
