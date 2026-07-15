from core.severity import get_severity, severity_sort_key, CRITICAL, HIGH, MEDIUM, LOW


def test_known_severities():
    assert get_severity("Potential Infinite Loop") == CRITICAL
    assert get_severity("Discouraged 'os.system' call") == HIGH
    assert get_severity("Generic Exception") == HIGH
    assert get_severity("Mutable Default Argument") == HIGH
    assert get_severity("Too Many Arguments") == MEDIUM
    assert get_severity("Excessive Nesting Depth") == MEDIUM
    assert get_severity("Complex List Comprehension") == LOW
    assert get_severity("Unused Import") == LOW
    assert get_severity("Magic Number") == LOW


def test_unknown_issue_type_defaults_to_medium():
    assert get_severity("Some Custom Rule Nobody Configured") == MEDIUM


def test_severity_sort_key_orders_critical_first():
    issue_types = ["Complex List Comprehension", "Potential Infinite Loop", "Too Many Arguments", "Generic Exception"]
    ordered = sorted(issue_types, key=severity_sort_key)
    assert ordered[0] == "Potential Infinite Loop"  # Critical
    assert ordered[1] == "Generic Exception"  # High
    assert ordered[-1] == "Complex List Comprehension"  # Low
