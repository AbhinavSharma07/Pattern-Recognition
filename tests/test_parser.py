from core.parser import analyze_source_code, check_syntax, load_config, DEFAULT_CONFIG


def smell_types(source, config=None):
    return [s.issue_type for s in analyze_source_code(source, "test.py", config or DEFAULT_CONFIG)]


def smells_by_type(source, issue_type, config=None):
    return [s for s in analyze_source_code(source, "test.py", config or DEFAULT_CONFIG) if s.issue_type == issue_type]


def test_too_many_arguments():
    source = "def f(a, b, c, d, e, f):\n    pass\n"
    assert "Too Many Arguments" in smell_types(source)


def test_ok_arguments_count_not_flagged():
    source = "def f(a, b):\n    pass\n"
    assert "Too Many Arguments" not in smell_types(source)


def test_long_function():
    body = "\n".join(f"    x{i} = {i}" for i in range(60))
    source = f"def f():\n{body}\n"
    assert "Long Function" in smell_types(source)


def test_bare_except_flagged():
    source = "try:\n    pass\nexcept:\n    pass\n"
    assert "Bare Except" in smell_types(source)


def test_bare_except_respects_config_toggle():
    source = "try:\n    pass\nexcept:\n    pass\n"
    config = {**DEFAULT_CONFIG, "check_bare_except": False}
    assert "Bare Except" not in smell_types(source, config)


def test_generic_exception_flagged():
    source = "try:\n    pass\nexcept Exception:\n    pass\n"
    assert "Generic Exception" in smell_types(source)


def test_specific_exception_not_flagged():
    source = "try:\n    pass\nexcept ValueError:\n    pass\n"
    types = smell_types(source)
    assert "Generic Exception" not in types
    assert "Bare Except" not in types


def test_excessive_nesting_depth():
    source = (
        "def f():\n"
        "    if True:\n"
        "        for i in range(1):\n"
        "            while True:\n"
        "                if True:\n"
        "                    pass\n"
    )
    assert "Excessive Nesting Depth" in smell_types(source)


def test_shallow_nesting_not_flagged():
    source = "def f():\n    if True:\n        pass\n"
    assert "Excessive Nesting Depth" not in smell_types(source)


def test_complex_list_comprehension():
    source = "valid_data = [x for x in range(100) if x % 2 == 0 if x % 3 == 0 if x % 5 == 0]\n"
    assert "Complex List Comprehension" in smell_types(source)


def test_custom_rule_disallowed_call():
    source = "import os\nos.system('rm -rf /')\n"
    config = {
        **DEFAULT_CONFIG,
        "custom_rules": [
            {"name": "Discouraged 'os.system' call", "type": "Call", "match": "os.system", "enabled": True}
        ],
    }
    assert "Discouraged 'os.system' call" in smell_types(source, config)


def test_custom_rule_disallowed_import():
    source = "import antigravity\n"
    config = {
        **DEFAULT_CONFIG,
        "custom_rules": [
            {"name": "Discouraged 'antigravity' import", "type": "Import", "match": "antigravity", "enabled": True}
        ],
    }
    assert "Discouraged 'antigravity' import" in smell_types(source, config)


def test_custom_rule_disallowed_decorator():
    source = "@discouraged_decorator\ndef f():\n    pass\n"
    config = {
        **DEFAULT_CONFIG,
        "custom_rules": [
            {"name": "Usage of discouraged decorator", "type": "Decorator", "match": "discouraged_decorator", "enabled": True}
        ],
    }
    assert "Usage of discouraged decorator" in smell_types(source, config)


def test_disabled_custom_rule_not_applied():
    source = "import os\nos.system('rm -rf /')\n"
    config = {
        **DEFAULT_CONFIG,
        "custom_rules": [
            {"name": "Discouraged 'os.system' call", "type": "Call", "match": "os.system", "enabled": False}
        ],
    }
    assert smell_types(source, config) == []


def test_clean_code_has_no_smells():
    source = "def add(a, b):\n    return a + b\n"
    assert smell_types(source) == []


def test_syntax_error_returns_empty_list():
    assert analyze_source_code("def f(:\n", "bad.py", DEFAULT_CONFIG) == []


def test_check_syntax_returns_none_for_valid_code():
    assert check_syntax("def add(a, b):\n    return a + b\n") is None


def test_check_syntax_reports_line_column_and_message_for_invalid_code():
    issue = check_syntax("def f(:\n    pass\n", "bad.py")
    assert issue is not None
    assert issue.line_number == 1
    assert issue.column_number > 0
    assert issue.message


def test_load_config_missing_file_returns_defaults(tmp_path):
    config = load_config(str(tmp_path / "does_not_exist.json"))
    assert config == DEFAULT_CONFIG


def test_load_config_reads_existing_file(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text('{"max_arguments": 2}', encoding="utf-8")
    config = load_config(str(config_file))
    assert config == {"max_arguments": 2}


def test_too_many_arguments_has_reason():
    source = "def f(a, b, c, d, e, f):\n    pass\n"
    smell = smells_by_type(source, "Too Many Arguments")[0]
    assert "6" in smell.reason
    assert "5" in smell.reason


def test_excessive_nesting_has_reason():
    source = (
        "def f():\n"
        "    if True:\n"
        "        for i in range(1):\n"
        "            while True:\n"
        "                if True:\n"
        "                    pass\n"
    )
    smell = smells_by_type(source, "Excessive Nesting Depth")[0]
    assert "4" in smell.reason and "3" in smell.reason


def test_infinite_loop_flagged_when_var_only_conditionally_updated():
    source = (
        "def f(c, d):\n"
        "    while c < 10:\n"
        "        if d == 5:\n"
        "            c += 1\n"
    )
    assert "Potential Infinite Loop" in smell_types(source)


def test_infinite_loop_not_flagged_when_unconditionally_updated():
    source = (
        "def f(c):\n"
        "    while c < 10:\n"
        "        c += 1\n"
    )
    assert "Potential Infinite Loop" not in smell_types(source)


def test_infinite_loop_not_flagged_with_unconditional_break():
    source = (
        "def f(c, d):\n"
        "    while True:\n"
        "        if d == 5:\n"
        "            c += 1\n"
        "        break\n"
    )
    assert "Potential Infinite Loop" not in smell_types(source)


def test_infinite_loop_respects_config_toggle():
    source = (
        "def f(c, d):\n"
        "    while c < 10:\n"
        "        if d == 5:\n"
        "            c += 1\n"
    )
    config = {**DEFAULT_CONFIG, "check_infinite_loops": False}
    assert "Potential Infinite Loop" not in smell_types(source, config)
