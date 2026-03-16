"""Tests for schedule text parser — pure function, no DB."""


from schoolai.skills.db.schedule_parser import parse_schedule_text


# ── Valid input ───────────────────────────────────────────────────────────────

def test_single_period():
    result = parse_schedule_text("07:00-08:30 3BT Matemáticas")
    assert len(result.periods) == 1
    assert len(result.errors) == 0
    p = result.periods[0]
    assert p.start_time == "07:00"
    assert p.end_time == "08:30"
    assert p.course_abbrev == "3bt"
    assert p.subject_raw == "Matemáticas"


def test_multiple_periods():
    text = (
        "07:00-08:30 3BT Matemáticas\n"
        "08:30-10:00 2BT Física\n"
        "10:30-12:00 10EGB Lengua y Literatura\n"
    )
    result = parse_schedule_text(text)
    assert len(result.periods) == 3
    assert len(result.errors) == 0
    assert result.periods[0].course_abbrev == "3bt"
    assert result.periods[1].course_abbrev == "2bt"
    assert result.periods[2].course_abbrev == "10egb"


def test_time_zero_padding():
    """'7:00-8:30' should be normalized to '07:00-08:30'."""
    result = parse_schedule_text("7:00-8:30 1BT Biología")
    assert result.periods[0].start_time == "07:00"
    assert result.periods[0].end_time == "08:30"


def test_course_aliases():
    cases = [
        ("07:00-08:30 3BT Matemáticas",  "3bt"),
        ("07:00-08:30 10EGB Ciencias",    "10egb"),
        ("07:00-08:30 prep Inicial",      "prep"),
        ("07:00-08:30 i1 Exploración",    "i1"),
        ("07:00-08:30 i2 Exploración",    "i2"),
        ("07:00-08:30 9egb Física",       "9egb"),
    ]
    for text, expected_abbrev in cases:
        result = parse_schedule_text(text)
        assert len(result.periods) == 1, f"No period parsed for: {text!r}"
        assert result.periods[0].course_abbrev == expected_abbrev


def test_subject_multiword():
    result = parse_schedule_text("07:00-08:30 2BT Lengua y Literatura")
    assert result.periods[0].subject_raw == "Lengua y Literatura"


def test_subject_before_course():
    """Course appears anywhere in the rest — subject is everything else."""
    result = parse_schedule_text("07:00-08:30 Matemáticas 3BT")
    assert len(result.periods) == 1
    assert result.periods[0].subject_raw == "Matemáticas"
    assert result.periods[0].course_abbrev == "3bt"


# ── Error handling ────────────────────────────────────────────────────────────

def test_empty_input():
    result = parse_schedule_text("")
    assert result.periods == []
    assert result.errors == []


def test_blank_lines_skipped():
    text = "\n\n07:00-08:30 3BT Matemáticas\n\n"
    result = parse_schedule_text(text)
    assert len(result.periods) == 1


def test_missing_time_format():
    result = parse_schedule_text("3BT Matemáticas sin hora")
    assert len(result.periods) == 0
    assert len(result.errors) == 1


def test_missing_course():
    result = parse_schedule_text("07:00-08:30 Matemáticas")
    assert len(result.periods) == 0
    assert len(result.errors) == 1


def test_missing_subject():
    result = parse_schedule_text("07:00-08:30 3BT")
    assert len(result.periods) == 0
    assert len(result.errors) == 1


def test_mixed_valid_and_invalid():
    text = (
        "07:00-08:30 3BT Matemáticas\n"   # válido
        "sin formato aquí\n"               # error
        "08:30-10:00 2BT Física\n"         # válido
        "10:00-11:30 cursoinvalido Arte\n"  # error — curso no reconocido
    )
    result = parse_schedule_text(text)
    assert len(result.periods) == 2
    assert len(result.errors) == 2


def test_error_lines_preserved():
    bad_line = "esta línea no tiene formato"
    result = parse_schedule_text(bad_line)
    assert bad_line in result.errors
