from core.metrics import compute_metrics


def test_compute_metrics_basic_counts():
    source = (
        "def f(a, b, c):\n"
        "    if a:\n"
        "        for i in range(b):\n"
        "            print(i)\n"
        "    return c\n"
    )
    m = compute_metrics(source)

    assert m.functions == 1
    assert m.max_arguments == 3
    assert m.num_loops == 1
    assert m.branches == 1
    assert m.function_calls == 2  # range(b), print(i)


def test_compute_metrics_returns_none_on_syntax_error():
    assert compute_metrics("def f(:\n") is None


def test_compute_metrics_nesting_depth_matches_parser_semantics():
    """A function nested inside another shouldn't inflate the outer function's
    own nesting number, matching core/parser.py's smell-detection semantics."""
    source = (
        "def outer():\n"
        "    if True:\n"
        "        def inner():\n"
        "            if True:\n"
        "                if True:\n"
        "                    if True:\n"
        "                        pass\n"
        "        return inner\n"
    )
    m = compute_metrics(source)
    # outer()'s own nesting is only 1 (the single `if True`); inner()'s deep
    # nesting must not leak into the file-wide max via outer's measurement,
    # but inner() is still its own function and does contribute its own depth.
    assert m.max_nesting_depth == 3  # inner()'s three nested ifs


def test_compute_metrics_detects_module_level_nesting_without_functions():
    source = "if True:\n    for i in range(10):\n        print(i)\n"
    m = compute_metrics(source)
    assert m.functions == 0
    assert m.max_nesting_depth == 2


def test_compute_metrics_cyclomatic_complexity_counts_decision_points():
    source = "def f(a, b):\n    if a and b:\n        return 1\n    return 0\n"
    m = compute_metrics(source)
    # baseline 1 + if + (and -> 1 extra operand) = 3
    assert m.cyclomatic_complexity == 3
