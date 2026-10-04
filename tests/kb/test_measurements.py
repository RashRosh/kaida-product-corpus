from kb.measurements import extract_measurements


def test_extracts_value_range_percentage_and_calibre():
    result = extract_measurements("Креветка 16/20 1,5-2 кг, глазурь 5%")
    assert result["calibres"] == ["16/20"]
    assert result["percentages"] == [5]
    assert result["measurements"] == [
        {"kind": "range", "unit": "kg", "raw": "1,5-2 кг", "min": 1.5, "max": 2}
    ]


def test_calibre_is_not_misread_as_measurement():
    result = extract_measurements("Креветка 10/20")
    assert result["measurements"] == []
    assert result["calibres"] == ["10/20"]
