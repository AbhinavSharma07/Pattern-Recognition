"""Static severity classification for detected code smells."""

CRITICAL = "Critical"
HIGH = "High"
MEDIUM = "Medium"
LOW = "Low"

_SEVERITY_BY_ISSUE_TYPE = {
    "Potential Infinite Loop": CRITICAL,
    "Discouraged 'os.system' call": HIGH,
    "Generic Exception": HIGH,
    "Bare Except": HIGH,
    "Mutable Default Argument": HIGH,
    "Too Many Arguments": MEDIUM,
    "Excessive Nesting Depth": MEDIUM,
    "Long Function": MEDIUM,
    "Complex List Comprehension": LOW,
    "Unused Import": LOW,
    "Magic Number": LOW,
}

_SEVERITY_ORDER = {CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3}


def get_severity(issue_type: str) -> str:
    """Unrecognized issue types (e.g. custom config.json rules) default to Medium."""
    return _SEVERITY_BY_ISSUE_TYPE.get(issue_type, MEDIUM)


def severity_sort_key(issue_type: str):
    """Sort key for ordering smells Critical -> High -> Medium -> Low."""
    return _SEVERITY_ORDER.get(get_severity(issue_type), 2)
