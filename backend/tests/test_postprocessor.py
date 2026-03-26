import pytest
from backend.app.services.ai.postprocessor import postprocess


# -----------------------------
# UID TESTS
# -----------------------------
def test_uid_clean_valid():
    data = {"aadhaar_number": "1234 5678 9012"}
    result = postprocess(data)

    assert result["aadhaar_number"]["valid"] is True
    assert result["aadhaar_number"]["normalized"] == "123456789012"


def test_uid_with_noise():
    data = {"aadhaar_number": "1234S6789O12"}  # S→5, O→0
    result = postprocess(data)

    assert result["aadhaar_number"]["valid"] is True
    assert result["aadhaar_number"]["normalized"] == "123456789012"


def test_uid_invalid_length():
    data = {"aadhaar_number": "12345678"}
    result = postprocess(data)

    assert result["aadhaar_number"]["valid"] is False


# -----------------------------
# DOB TESTS
# -----------------------------
def test_dob_normalization():
    data = {"dob": "1-1-2000"}
    result = postprocess(data)

    assert result["dob"]["normalized"] == "01/01/2000"
    assert result["dob"]["valid"] is True


def test_dob_invalid():
    data = {"dob": "32/13/2000"}
    result = postprocess(data)

    assert result["dob"]["valid"] is False


# -----------------------------
# NAME TESTS
# -----------------------------
def test_name_cleaning():
    data = {"name": "NAME: MANZIL SHARMA"}
    result = postprocess(data)

    assert result["name"]["normalized"] == "Manzil Sharma"
    assert result["name"]["valid"] is True


def test_name_invalid_noise():
    data = {"name": "जाम वहोएते ..."}
    result = postprocess(data)

    assert result["name"]["valid"] is False


# -----------------------------
# GENDER TESTS
# -----------------------------
def test_gender_mapping():
    data = {"gender": "MALE"}
    result = postprocess(data)

    assert result["gender"]["normalized"] == "Male"
    assert result["gender"]["valid"] is True


def test_gender_invalid():
    data = {"gender": "XYZ"}
    result = postprocess(data)

    assert result["gender"]["valid"] is False


# -----------------------------
# ADDRESS TESTS
# -----------------------------
def test_address_cleaning():
    data = {"address": "123, Street | Bangalore"}
    result = postprocess(data)

    assert "Street Bangalore" in result["address"]["normalized"]
    assert result["address"]["valid"] is True
