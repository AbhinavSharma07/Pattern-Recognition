from core.sandbox import execute_tests

PASSING_MODULE = "def add(a, b):\n    return a + b\n"
PASSING_TEST = "from target_module import add\n\ndef test_add():\n    assert add(2, 3) == 5\n"

FAILING_TEST = "from target_module import add\n\ndef test_add():\n    assert add(2, 3) == 999\n"

BROKEN_MODULE = "def add(a, b)\n    return a + b\n"  # missing colon -> SyntaxError on import


def test_execute_tests_success():
    result = execute_tests(PASSING_MODULE, PASSING_TEST)
    assert result["success"] is True
    assert "1 passed" in result["output"]


def test_execute_tests_failure():
    result = execute_tests(PASSING_MODULE, FAILING_TEST)
    assert result["success"] is False
    assert "failed" in result["output"].lower()


def test_execute_tests_syntax_error_in_refactor():
    result = execute_tests(BROKEN_MODULE, PASSING_TEST)
    assert result["success"] is False
