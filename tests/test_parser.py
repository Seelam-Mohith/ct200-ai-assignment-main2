from app.parser import parse
T, ROOT, NODES = parse("data/ct200_manual_v2.pdf")
by = {n.number: n for n in NODES}

def test_title_joined_across_three_lines():
    assert T.startswith("CardioTrack CT-200") and T.endswith("User Manual")

def test_bold_body_size_headings_detected():          # 3.2 / 3.4 are 11pt bold
    assert "3.2" in by and "3.4" in by and by["3.4"].heading == "Auto Shutoff"

def test_skipped_level_parented_and_flagged():        # 2.1 -> 2.1.1.1
    n = by["2.1.1.1"]; assert n.parent.number == "2.1" and n.level == 4
    assert any("skipped_level" in w for w in n.warnings)

def test_out_of_order_sections_flagged_not_reordered():  # 3.4 appears before 3.3
    assert any("out_of_order" in w for w in by["3.3"].warnings)
    assert by["3.3"].parent.number == "3" == by["3.4"].parent.number

def test_duplicate_heading_two_distinct_paths():      # "Error Codes" in 4.2 and 7.1
    a, b = by["4.2"], by["7.1"]
    assert a.heading == b.heading and a.path != b.path
    assert a.parent.number == "4" and b.parent.number == "7"

def test_list_items_are_not_headings():
    assert "1. Normal" in by["3.3"].body and "5. Hypertensive Crisis" in by["3.3"].body

def test_ligatures_and_nb_hyphen_normalised():
    assert "ﬁ" not in by["2.2"].body and "CT-200" in by["3.4"].body

def test_section_split_across_pages_not_lost():       # 4.3 continues on page 5
    assert "cannot be silenced" in by["4.3"].body

def test_table_flagged():
    assert any("table_present" in w for w in by["4.2"].warnings)
