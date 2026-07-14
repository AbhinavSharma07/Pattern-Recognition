import ast
import json
from pathlib import Path
from typing import List, Dict, Any, Set
from collections import defaultdict
from .schemas import CodeSmell
from .metrics import max_nesting_depth as _shared_max_nesting_depth

DEFAULT_CONFIG: Dict[str, Any] = {
    "max_arguments": 5,
    "max_function_length": 50,
    "max_nesting_depth": 3,
    "check_bare_except": True,
    "check_generic_exception": True,
    "max_list_comp_ifs": 2,
    "check_infinite_loops": True,
    "custom_rules": [],
}


class AntiPatternVisitor(ast.NodeVisitor):
    """
    An AST visitor that detects both built-in and custom-defined code smells.
    """
    def __init__(self, source_code: str, file_name: str, config: Dict[str, Any]):
        self.file_name = file_name
        self.source_lines = source_code.splitlines()
        self.smells: List[CodeSmell] = []
        self.config = {**DEFAULT_CONFIG, **(config or {})}

        # Pre-process custom rules into a more efficient structure for lookups.
        # Rule shape (as used in config.json): {"name", "type": "Call"|"Import"|"Decorator", "match", "enabled"}
        self.custom_rules_by_type = defaultdict(list)
        for rule in self.config.get("custom_rules", []):
            if rule.get("enabled", True) and "type" in rule and "match" in rule:
                self.custom_rules_by_type[rule["type"]].append(rule)

    def _get_node_code(self, node: ast.AST) -> str:
        """Extracts the raw source code for a given AST node."""
        try:
            return ast.get_source_segment("\n".join(self.source_lines), node)
        except (TypeError, ValueError):
            # Fallback for nodes that don't have a direct source segment
            return "..."

    def _add_smell(self, issue_type: str, target_name: str, node: ast.AST, reason: str = ""):
        self.smells.append(CodeSmell(
            issue_type=issue_type,
            target_name=target_name,
            raw_code=self._get_node_code(node),
            line_number=node.lineno,
            file_name=self.file_name,
            reason=reason,
        ))

    @staticmethod
    def _get_dotted_call_name(node: ast.Call) -> str:
        """Reconstructs a dotted call name (e.g. 'os.system') from a Call node."""
        func = node.func
        parts = []
        while isinstance(func, ast.Attribute):
            parts.append(func.attr)
            func = func.value
        if isinstance(func, ast.Name):
            parts.append(func.id)
        return ".".join(reversed(parts)) if parts else "unknown"

    @staticmethod
    def _get_decorator_name(node: ast.expr) -> str:
        """Extracts a usable name from a decorator expression."""
        if isinstance(node, ast.Call):
            node = node.func
        if isinstance(node, ast.Attribute):
            return node.attr
        if isinstance(node, ast.Name):
            return node.id
        return "unknown"

    def _max_nesting_depth(self, node: ast.AST) -> int:
        """Computes the deepest nesting of control-flow blocks within a function body."""
        return _shared_max_nesting_depth(node)

    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Checks for long functions, too many arguments, deep nesting, and disallowed decorators."""
        max_len = self.config.get("max_function_length", 50)
        length = node.end_lineno - node.lineno
        if length > max_len:
            self._add_smell(
                "Long Function", node.name, node,
                reason=f"Function spans {length} lines. Configured threshold = {max_len}.",
            )

        max_args = self.config.get("max_arguments", 5)
        num_args = len(node.args.args)
        if num_args > max_args:
            self._add_smell(
                "Too Many Arguments", node.name, node,
                reason=f"Function has {num_args} positional parameters. Configured threshold = {max_args}.",
            )

        max_depth = self.config.get("max_nesting_depth", 3)
        depth = self._max_nesting_depth(node)
        if depth > max_depth:
            self._add_smell(
                "Excessive Nesting Depth", node.name, node,
                reason=f"Maximum nesting depth = {depth}. Configured threshold = {max_depth}.",
            )

        for decorator in node.decorator_list:
            decorator_name = self._get_decorator_name(decorator)
            for rule in self.custom_rules_by_type.get("Decorator", []):
                if rule.get("match") == decorator_name:
                    self._add_smell(
                        rule.get("name", "Discouraged decorator"), decorator_name, node,
                        reason=f"Matches configured rule '{rule.get('name', decorator_name)}' (decorator: @{decorator_name}).",
                    )

        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        """Checks for bare 'except:' clauses and overly broad 'except Exception:' clauses."""
        if node.type is None:
            if self.config.get("check_bare_except", True):
                self._add_smell(
                    "Bare Except", "except block", node,
                    reason="Bare 'except:' catches every exception, including SystemExit and KeyboardInterrupt.",
                )
        elif isinstance(node.type, ast.Name) and node.type.id == "Exception":
            if self.config.get("check_generic_exception", True):
                self._add_smell(
                    "Generic Exception", "except Exception block", node,
                    reason="Catches the broad 'Exception' class, which can mask unrelated bugs.",
                )
        self.generic_visit(node)

    def visit_ListComp(self, node: ast.ListComp):
        """Checks for list comprehensions with an excessive number of 'if' filters."""
        max_ifs = self.config.get("max_list_comp_ifs", 2)
        total_ifs = sum(len(gen.ifs) for gen in node.generators)
        if total_ifs > max_ifs:
            self._add_smell(
                "Complex List Comprehension", "list comprehension", node,
                reason=f"List comprehension has {total_ifs} 'if' filter(s). Configured threshold = {max_ifs}.",
            )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        """Checks for disallowed function calls based on custom rules."""
        dotted_name = self._get_dotted_call_name(node)
        simple_name = dotted_name.rsplit(".", 1)[-1]

        for rule in self.custom_rules_by_type.get("Call", []):
            pattern = rule.get("match")
            if pattern in (dotted_name, simple_name):
                self._add_smell(
                    rule.get("name", "Disallowed function call"), dotted_name, node,
                    reason=f"Matches configured rule '{rule.get('name', dotted_name)}' (call: {dotted_name}).",
                )
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import):
        """Checks for disallowed 'import <module>' statements."""
        for alias in node.names:
            module_name = alias.name
            for rule in self.custom_rules_by_type.get("Import", []):
                if rule.get("match") == module_name:
                    self._add_smell(
                        rule.get("name", "Disallowed import"), module_name, node,
                        reason=f"Matches configured rule '{rule.get('name', module_name)}' (import: {module_name}).",
                    )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        """Checks for disallowed 'from <module> import ...' statements."""
        module_name = node.module or ""
        for rule in self.custom_rules_by_type.get("Import", []):
            if rule.get("match") == module_name:
                self._add_smell(
                    rule.get("name", "Disallowed 'from' import"), module_name, node,
                    reason=f"Matches configured rule '{rule.get('name', module_name)}' (from-import: {module_name}).",
                )
        self.generic_visit(node)

    def visit_While(self, node: ast.While):
        """
        Heuristic check for a common infinite-loop pattern: the loop condition's
        variable(s) are only ever updated inside a conditional branch, with no
        unconditional break/return anywhere in the loop body.

        This is a best-effort heuristic, not a soundness guarantee -- proving a
        loop terminates is undecidable in general. It catches one common,
        genuine mistake (e.g. `while c < 10: if d == 5: c += 1`, which never
        terminates if `d != 5`) but can both miss real infinite loops with more
        complex control flow and, more rarely, flag loops a human would
        recognize as safe. Always reported as "Potential", never asserted as fact.
        """
        if self.config.get("check_infinite_loops", True):
            condition_vars = {n.id for n in ast.walk(node.test) if isinstance(n, ast.Name)}
            if condition_vars and self._loop_var_only_conditionally_updated(node, condition_vars):
                self._add_smell(
                    "Potential Infinite Loop", "while loop", node,
                    reason=(
                        f"Loop variable(s) {sorted(condition_vars)} appear to be modified only inside a "
                        "conditional branch, with no unconditional break/return in the loop body. "
                        "The loop may never terminate if that branch is never taken."
                    ),
                )
        self.generic_visit(node)

    @staticmethod
    def _loop_var_only_conditionally_updated(node: ast.While, condition_vars: Set[str]) -> bool:
        """
        Looks only at the loop body's top-level statements (not nested inside
        further if/for/while blocks, which would make an update conditional
        anyway). Returns True (flag as suspicious) when none of them
        unconditionally update a condition variable or unconditionally exit
        the loop.
        """
        for stmt in node.body:
            if isinstance(stmt, (ast.Break, ast.Return)):
                return False  # can exit unconditionally -- not flaggable as infinite
            if isinstance(stmt, ast.Assign):
                targets = {t.id for t in stmt.targets if isinstance(t, ast.Name)}
                if targets & condition_vars:
                    return False  # unconditionally updated
            if isinstance(stmt, ast.AugAssign) and isinstance(stmt.target, ast.Name):
                if stmt.target.id in condition_vars:
                    return False
        return True


def analyze_source_code(source_code: str, file_name: str, config: Dict[str, Any] = None) -> List[CodeSmell]:
    """
    Parses source code into an AST and uses the AntiPatternVisitor to find smells.
    """
    try:
        tree = ast.parse(source_code)
        visitor = AntiPatternVisitor(source_code, file_name, config or {})
        visitor.visit(tree)
        return visitor.smells
    except SyntaxError as e:
        print(f"Could not parse {file_name} due to a syntax error: {e}")
        return []


def load_config(config_path: str) -> Dict[str, Any]:
    """
    Loads the configuration file from a given path.
    Returns a default config if the file doesn't exist.
    """
    if Path(config_path).exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    print(f"Warning: Config file not found at '{config_path}'. Using default settings.")
    return dict(DEFAULT_CONFIG)
