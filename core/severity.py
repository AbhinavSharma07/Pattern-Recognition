"""
Static severity classification for detected code smells.

Severity is a pure function of issue_type -- deterministic and rule-based,
same as detection itself. It's kept out of the CodeSmell schema (rather than
stored at detection time) since it's cheap to derive on demand and this
avoids touching every CodeSmell construction site across the codebase.
"""

CRITICAL = "Critical"
HIGH = "High"
MEDIUM = "Medium"
LOW = "Low"

_SEVERITY_BY_ISSUE_TYPE = {
    "Potential Infinite Loop": CRITICAL,
    "Discouraged 'os.system' call": HIGH,
    "Generic Exception": HIGH,
    "Bare Except": HIGH,
    "Too Many Arguments": MEDIUM,
    "Excessive Nesting Depth": MEDIUM,
    "Long Function": MEDIUM,
    "Complex List Comprehension": LOW,
}

_SEVERITY_ORDER = {CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3}


def get_severity(issue_type: str) -> str:
    """
    Returns the severity for a built-in issue_type. Custom rules (Call/Import/
    Decorator, user-defined in config.json) and any other unrecognized
    issue_type default to Medium -- there's no principled way to guess a
    user-defined rule's severity, and Medium is a reasonable, non-alarming
    default rather than silently treating unknown issues as Low (understating
    them) or High (overstating them).
    """
    return _SEVERITY_BY_ISSUE_TYPE.get(issue_type, MEDIUM)


def severity_sort_key(issue_type: str):
    """Sort key for ordering smells Critical -> High -> Medium -> Low."""
    return _SEVERITY_ORDER.get(get_severity(issue_type), 2)
