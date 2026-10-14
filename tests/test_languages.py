from utils.languages import language_name

def test_language_name_known():
    assert language_name("en") == "English"
    assert language_name("hi") == "Hindi"
    assert language_name("hinglish") == "Hinglish"
    assert language_name("es") == "Spanish"
    assert language_name("und") == "Undetected"

def test_language_name_casing_and_whitespace():
    assert language_name(" EN ") == "English"
    assert language_name("Hi") == "Hindi"

def test_language_name_unknown():
    assert language_name("xyz") == "XYZ"
    assert language_name("") == "Unknown"
    assert language_name(None) == "Unknown"
