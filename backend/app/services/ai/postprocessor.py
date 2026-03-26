import re
from datetime import datetime


# -----------------------------
# Base Processor
# -----------------------------
class BaseProcessor:
    def clean(self, text: str) -> str:
        if not text:
            return ""
        return text.strip()

    def correct(self, text: str) -> str:
        return text
    def validate(self, text: str) -> bool:
        raise NotImplementedError

    def normalize(self, text: str):
        raise NotImplementedError

    def confidence(self, raw: str, normalized: str, valid: bool) -> float:
        if not raw:
            return 0.0
        if valid:
            return 0.9
        return 0.3

    def process(self, text: str, field: str):
        raw = text
        text = self.clean(text)
        corrected = self.correct(text)

        valid = self.validate(corrected)
        normalized = self.normalize(corrected) if valid else None
        conf = self.confidence(raw, normalized, valid)

        return {
            "field": field,
            "raw": raw,
            "normalized": normalized,
            "valid": valid,
            "confidence": conf,
        }


# -----------------------------
# UID Processor
# -----------------------------
class UIDProcessor(BaseProcessor):
    UID_REGEX = re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")

    def validate(self, text: str) -> bool:
        digits = re.sub(r"\D", "", text)
        return len(digits) == 12

    def normalize(self, text: str) -> str:
        digits = re.sub(r"\D", "", text)
        return digits  # store as continuous

    def confidence(self, raw, normalized, valid):
        if valid and normalized:
            return 0.95
        return 0.2

    def correct(self, text: str) -> str:
        corrections = {
            "O": "0",
            "I": "1",
            "L": "1",
            "S": "5",
            "B": "8",
        }
        return "".join(corrections.get(c, c) for c in text)


# -----------------------------
# DOB Processor
# -----------------------------
class DOBProcessor(BaseProcessor):
    DOB_REGEX = re.compile(r"\b\d{1,2}[-/\s]\d{1,2}[-/\s]\d{4}\b")

    def normalize(self, text: str):
        match = self.DOB_REGEX.search(text)
        if not match:
            return None

        parts = re.split(r"[-/\s]", match.group())

        try:
            day, month, year = parts
            day = int(day)
            month = int(month)

            # normalize to DD/MM/YYYY
            date_obj = datetime(int(year), month, day)
            return date_obj.strftime("%d/%m/%Y")
        except:
            return None

    def validate(self, text: str) -> bool:
        return self.normalize(text) is not None

    def confidence(self, raw, normalized, valid):
        return 0.9 if valid else 0.3


# -----------------------------
# Name Processor
# -----------------------------
class NameProcessor(BaseProcessor):
    def clean(self, text: str) -> str:
        text = super().clean(text)
        text = re.sub(r"(NAME[:\-]?)", "", text, flags=re.IGNORECASE)
        return text.strip()

    def validate(self, text: str) -> bool:
        return bool(re.search(r"[A-Za-z]{2,}",text))

    def normalize(self, text: str) -> str:
        return text.title()

    def confidence(self, raw, normalized, valid):
        return 0.85 if valid else 0.4


# -----------------------------
# Gender Processor
# -----------------------------
class GenderProcessor(BaseProcessor):
    MAP = {
        "m": "Male",
        "male": "Male",
        "f": "Female",
        "female": "Female",
        "other": "Other",
    }

    def validate(self, text: str) -> bool:
        return text.lower() in self.MAP

    def normalize(self, text: str):
        return self.MAP.get(text.lower())

    def confidence(self, raw, normalized, valid):
        return 0.95 if valid else 0.3


# -----------------------------
# Address Processor
# -----------------------------
class AddressProcessor(BaseProcessor):
    def validate(self, text: str) -> bool:
        return len(text) > 10

    def normalize(self, text: str) -> str:
        text = re.sub(r"[|,:]+", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def confidence(self, raw, normalized, valid):
        return 0.8 if valid else 0.4


# -----------------------------
# Dispatcher
# -----------------------------
PROCESSORS = {
    "aadhaar_number": UIDProcessor(),
    "uid": UIDProcessor(),
    "dob": DOBProcessor(),
    "name": NameProcessor(),
    "gender": GenderProcessor(),
    "address": AddressProcessor(),
}


# -----------------------------
# Main Entry Function
# -----------------------------
def postprocess(fields: dict):
    """
    fields = {
        "uid": "...",
        "dob": "...",
        ...
    }
    """
    results = {}

    for field, value in fields.items():
        processor = PROCESSORS.get(field)

        if not processor:
            continue

        results[field] = processor.process(value, field)

    return results
