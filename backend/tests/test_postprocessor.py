from backend.app.services.ai.postprocessor import (
    AddressProcessor,
    BaseProcessor,
    DOBProcessor,
    GenderProcessor,
    NameProcessor,
    UIDProcessor,
    postprocess,
)


def test_base_processor_process_returns_invalid_payload_for_empty_text() -> None:
    class DummyProcessor(BaseProcessor):
        def validate(self, text: str) -> bool:
            return text == "valid"

        def normalize(self, text: str):
            return text.upper()

    result = DummyProcessor().process("", "dummy")

    assert result == {
        "field": "dummy",
        "raw": "",
        "normalized": None,
        "valid": False,
        "confidence": 0.0,
    }


def test_uid_processor_normalizes_clean_aadhaar() -> None:
    result = postprocess({"aadhaar_number": "1234 5678 9012"})

    assert result["aadhaar_number"]["valid"] is True
    assert result["aadhaar_number"]["normalized"] == "123456789012"
    assert result["aadhaar_number"]["confidence"] == 0.95


def test_uid_processor_corrects_common_ocr_noise() -> None:
    result = postprocess({"aadhaar_number": "I234 S678 9O1B"})

    assert result["aadhaar_number"]["valid"] is True
    assert result["aadhaar_number"]["normalized"] == "123456789018"


def test_uid_processor_rejects_wrong_length() -> None:
    result = postprocess({"aadhaar_number": "12345678"})

    assert result["aadhaar_number"]["valid"] is False
    assert result["aadhaar_number"]["normalized"] is None
    assert result["aadhaar_number"]["confidence"] == 0.2


def test_dob_processor_normalizes_supported_separators() -> None:
    result = postprocess({"dob": "1-1-2000"})

    assert result["dob"]["valid"] is True
    assert result["dob"]["normalized"] == "01/01/2000"
    assert result["dob"]["confidence"] == 0.9


def test_dob_processor_rejects_impossible_dates() -> None:
    result = postprocess({"dob": "32/13/2000"})

    assert result["dob"]["valid"] is False
    assert result["dob"]["normalized"] is None
    assert result["dob"]["confidence"] == 0.3


def test_dob_processor_rejects_missing_date_pattern() -> None:
    result = postprocess({"dob": "DOB unavailable"})

    assert result["dob"]["valid"] is False
    assert result["dob"]["normalized"] is None


def test_name_processor_removes_label_and_title_cases_text() -> None:
    result = postprocess({"name": "NAME: MANZIL SHARMA"})

    assert result["name"]["valid"] is True
    assert result["name"]["normalized"] == "Manzil Sharma"
    assert result["name"]["confidence"] == 0.85


def test_name_processor_rejects_non_latin_noise() -> None:
    result = postprocess({"name": "जाम वहोएते ..."})

    assert result["name"]["valid"] is False
    assert result["name"]["normalized"] is None
    assert result["name"]["confidence"] == 0.4


def test_gender_processor_maps_supported_values_case_insensitively() -> None:
    result = postprocess({"gender": "MALE"})

    assert result["gender"]["valid"] is True
    assert result["gender"]["normalized"] == "Male"
    assert result["gender"]["confidence"] == 0.95


def test_gender_processor_rejects_unknown_value() -> None:
    result = postprocess({"gender": "XYZ"})

    assert result["gender"]["valid"] is False
    assert result["gender"]["normalized"] is None
    assert result["gender"]["confidence"] == 0.3


def test_address_processor_normalizes_punctuation_and_spacing() -> None:
    result = postprocess({"address": "221B, Baker Street | Bengaluru"})

    assert result["address"]["valid"] is True
    assert result["address"]["normalized"] == "221B Baker Street Bengaluru"
    assert result["address"]["confidence"] == 0.8


def test_address_processor_rejects_short_values() -> None:
    result = postprocess({"address": "Too short"})

    assert result["address"]["valid"] is False
    assert result["address"]["normalized"] is None
    assert result["address"]["confidence"] == 0.4


def test_postprocess_skips_unknown_fields() -> None:
    result = postprocess({"unsupported": "value", "uid": "1234 5678 9012"})

    assert "unsupported" not in result
    assert result["uid"]["normalized"] == "123456789012"


def test_direct_processor_methods_cover_edge_inputs() -> None:
    uid = UIDProcessor()
    dob = DOBProcessor()
    name = NameProcessor()
    gender = GenderProcessor()
    address = AddressProcessor()

    assert uid.correct("O1S8L") == "01581"
    assert dob.normalize("DOB 05/07/1999") == "05/07/1999"
    assert name.clean("Name- JOHN DOE") == "JOHN DOE"
    assert gender.normalize("other") == "Other"
    assert address.normalize("Flat 2, Block A: Sector 9") == "Flat 2 Block A Sector 9"
