import os
from backend.app.services.ai.preprocessing import preprocess_document

folder = "data/aadhaar/test/images"

for i, img in enumerate(os.listdir(folder)[:10]):
    path = os.path.join(folder, img)
    try:
        output = preprocess_document(path)
        print(f"{i+1}: OK - {img} - shape {output.shape}")
    except Exception as e:
        print(f"{i+1}: FAIL - {img} - {e}")
