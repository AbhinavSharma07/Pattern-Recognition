import ast
import json
from typing import List, Dict, Any
from pathlib import Path
from .schemas import CodeSmell

DEFAULT_CONFIG = {
    "max_arguments": 5,
    "max_nesting_depth": 3,
    "check_bare_except": True
}

def load_config(config_path: str = "config.json") -> Dict[str, Any]:
    path = Path(config_path)
    if path.exists() and path.is_file():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading config {config_path}: {e}. Using defaults.")
    return DEFAULT_CONFIG

class AntiPatternVisitor(ast.NodeVisitor):
    def __init__(self, file_name: str, source_code: str, config: Dict[str, Any] = None):
        self.file_name = file_name
        self.source_code = source_code
        self.smells: List[CodeSmell] = []
        self.config = config or DEFAULT_CONFIG

    def visit_FunctionDef(self, node: ast.FunctionDef):
        # Pattern 1: Check for excessive arguments
        max_args = self.config.get("max_arguments", 5)
        if len(node.args.args) > max_args:
            self._record_smell(node, f"Excessive Arguments (> {max_args})")

        # Pattern 2: Check for complex control flow nesting
        max_nesting = self.config.get("max_nesting_depth", 3)
        nesting_depth = self._calculate_max_nesting(node.body)
        if nesting_depth > max_nesting:
            self._record_smell(node, f"Deep Nesting (depth: {nesting_depth}, max allowed: {max_nesting})")

        # Continue traversing down the tree
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        # Pattern 3: Check for bare except clauses
        if self.config.get("check_bare_except", True) and node.type is None:
            self._record_smell(node, "Bare 'except' clause detected")
        
        self.generic_visit(node)

    def _calculate_max_nesting(self, nodes: List[ast.stmt], current_depth: int = 0) -> int:
        """Recursively calculates the maximum nesting depth of control flow blocks."""
        max_depth = current_depth
        for n in nodes:
            if isinstance(n, (ast.If, ast.For, ast.While, ast.With, ast.Try)):
                depth = self._calculate_max_nesting(n.body, current_depth + 1)
                max_depth = max(max_depth, depth)
            elif isinstance(n, ast.Try) and getattr(n, 'handlers', None):
                # Check inside except/finally blocks
                for handler in n.handlers:
                    depth = self._calculate_max_nesting(handler.body, current_depth + 1)
                    max_depth = max(max_depth, depth)
        return max_depth

    def _record_smell(self, node: ast.AST, issue: str):
        """Helper method to extract the code and save the CodeSmell."""
        try:
            # Extract the exact string from the original source file to allow string replacement later
            code_snippet = ast.get_source_segment(self.source_code, node) or ast.unparse(node)
        except Exception:
            code_snippet = "# Could not extract raw code."
        
        target_name = getattr(node, 'name', 'Unnamed Block')
        
        smell = CodeSmell(
            file_name=self.file_name,
            target_name=target_name,
            line_number=getattr(node, 'lineno', -1),
            issue_type=issue,
            raw_code=code_snippet
        )
        self.smells.append(smell)

def analyze_source_code(source_code: str, file_name: str = "temp.py", config: Dict[str, Any] = None) -> List[CodeSmell]:
    """
    Entry point for the static analysis engine.
    Parses the source code string and returns a list of detected CodeSmells.
    """
    tree = ast.parse(source_code)
    visitor = AntiPatternVisitor(file_name, source_code, config)
    visitor.visit(tree)
    return visitor.smells