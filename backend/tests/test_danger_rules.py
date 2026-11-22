from app.rules import detect_danger_signs


def test_detects_pregnancy_danger_phrase():
    flags = detect_danger_signs("The mother has heavy bleeding and severe headache.", category="pregnancy")
    rule_ids = {f["rule_id"] for f in flags}
    assert "PREG-01" in rule_ids
    assert "PREG-02" in rule_ids
    assert all(f.get("guideline_citation") for f in flags)
    assert all(f.get("applies_to") == "mother" for f in flags)


def test_detects_newborn_danger_phrase():
    flags = detect_danger_signs("Baby has high fever and poor feeding", category="newborn")
    rule_ids = {f["rule_id"] for f in flags}
    assert "NEWB-01" in rule_ids
    assert "NEWB-02" in rule_ids


def test_negation_suppresses_danger_sign():
    flags = detect_danger_signs("No bleeding, no fever, denies severe headache", category="pregnancy")
    assert flags == []


def test_negated_and_positive_mixed():
    flags = detect_danger_signs("No bleeding but she has severe headache", category="pregnancy")
    rule_ids = {f["rule_id"] for f in flags}
    assert "PREG-01" not in rule_ids
    assert "PREG-02" in rule_ids


def test_normal_text_no_false_positive():
    flags = detect_danger_signs("Mother and baby are doing well. No complaints today.", category="general")
    assert flags == []
