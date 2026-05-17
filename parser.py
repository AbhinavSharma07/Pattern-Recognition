import ast
from typing import List
from .schemas import CodeSmell

class AntiPatternVisitor(ast.NodeVisitor):
    def __init__(self, file_name: str):
        self.file_name = file_name
        self.smells: List[CodeSmell] = []

    def visit_FunctionDef(self, node: ast.FunctionDef):
        # Pattern 1: Check for excessive arguments (> 5)
        if len(node.args.args) > 5:
            self._record_smell(node, "Excessive Arguments (> 5)")

        # Pattern 2: Check for complex control flow nesting (> 3)
        nesting_depth = self._calculate_max_nesting(node.body)
        if nesting_depth > 3:
            self._record_smell(node, f"Deep Nesting (depth: {nesting_depth})")

        # Continue traversing down the tree
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        # Pattern 3: Check for bare except clauses
        if node.type is None:
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
            # ast.unparse requires Python 3.9+ and converts the node back to a string
            code_snippet = ast.unparse(node)
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

def analyze_source_code(source_code: str, file_name: str = "temp.py") -> List[CodeSmell]:
    """
    Entry point for the static analysis engine.
    Parses the source code string and returns a list of detected CodeSmells.
    """
    tree = ast.parse(source_code)
    visitor = AntiPatternVisitor(file_name)
    visitor.visit(tree)
    return visitor.smells