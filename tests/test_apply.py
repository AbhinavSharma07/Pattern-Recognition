import ast

from core.schemas import CodeSmell, RefactorProposal
from agents.main import apply_validated_fixes


def _result(target_name, raw_code, refactored_code, validated=True, required_imports=None):
    return {
        "smell": CodeSmell(file_name="f.py", target_name=target_name, line_number=1, issue_type="x", raw_code=raw_code),
        "refactor": RefactorProposal(
            original_function_name=target_name,
            explanation="...",
            refactored_code=refactored_code,
            required_imports=required_imports or [],
        ),
        "test": None,
        "validated": validated,
    }


def test_applies_single_validated_fix():
    source = "def f(a, b):\n    return a + b\n"
    results = [_result("f", source, "def f(*args):\n    return sum(args)\n")]

    new_source, count = apply_validated_fixes(source, results)

    assert count == 1
    assert "def f(*args):" in new_source
    ast.parse(new_source)


def test_skips_unvalidated_fix():
    source = "def f(a, b):\n    return a + b\n"
    results = [_result("f", source, "def f(*args):\n    return sum(args)\n", validated=False)]

    new_source, count = apply_validated_fixes(source, results)

    assert count == 0
    assert new_source == source


def test_multi_statement_refactor_applies_via_libcst():
    """Regression test: a refactor that introduces a helper function alongside
    the fix used to fail to parse (parse_statement only accepts one statement)
    and silently fall back to a naive string-replace. It should now apply
    cleanly through libcst's FlattenSentinel path."""
    source = "def f(a, b):\n    return a + b\n"
    refactored = (
        "def _helper(a, b):\n"
        "    return a + b\n\n\n"
        "def f(a, b):\n"
        "    return _helper(a, b)\n"
    )
    results = [_result("f", source, refactored)]

    new_source, count = apply_validated_fixes(source, results)

    assert count == 1
    assert "_helper" in new_source
    ast.parse(new_source)


def test_overlapping_fixes_second_one_skipped_without_corrupting_file():
    """Regression test for the real corruption bug: two validated fixes touch
    overlapping code (a whole-function rewrite, then a fix whose raw_code
    happens to still match inside that rewrite but whose replacement would
    break syntax there). The second fix must be skipped, not silently written
    as broken Python."""
    source = (
        "def f():\n"
        "    try:\n"
        "        pass\n"
        "    except Exception as e:\n"
        "        print(e)\n"
    )
    # The whole-function rewrite (matched by libcst on target_name "f") keeps the
    # except block's text unchanged, so it's still present for the second fix to
    # (mistakenly) match against.
    whole_function_rewrite = (
        "def f():\n"
        "    try:\n"
        "        pass\n"
        "    except Exception as e:\n"
        "        print(e)\n"
        "    extra_call()\n"
    )
    conflicting_raw_code = "    except Exception as e:\n        print(e)\n"
    # Deliberately incomplete replacement (an except clause with no body) --
    # simulates a fix that is fine in isolation but invalid once the source
    # around it has already changed.
    conflicting_replacement = "    except Exception as e:\n"

    results = [
        _result("f", source, whole_function_rewrite),
        _result("except block", conflicting_raw_code, conflicting_replacement),
    ]

    new_source, count = apply_validated_fixes(source, results)

    assert count == 1  # only the first, non-conflicting fix was kept
    assert "extra_call()" in new_source
    ast.parse(new_source)  # must still be valid Python


def test_required_imports_collected_via_libcst_path():
    """Regression test: required_imports used to only be collected on the
    no-libcst fallback branch, never when libcst successfully applied a fix."""
    source = "def f(a, b):\n    return a + b\n"
    results = [_result("f", source, "def f(*args):\n    return sum(args)\n", required_imports=["import functools"])]

    new_source, count = apply_validated_fixes(source, results)

    assert count == 1
    assert new_source.startswith("import functools")
