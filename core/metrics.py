"""Deterministic, AST-derived metrics for before/after refactor comparison."""
import ast
from dataclasses import dataclass, asdict
from typing import Optional

_NESTING_BOUNDARY_NODES = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith)
_FUNCTION_LIKE = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)


def max_nesting_depth(node: ast.AST) -> int:
    """Deepest control-flow nesting within `node`, excluding nested functions/lambdas/classes."""
    def depth(n: ast.AST) -> int:
        child_depths = [
            depth(child) + (1 if isinstance(child, _NESTING_BOUNDARY_NODES) else 0)
            for child in ast.iter_child_nodes(n)
            if not isinstance(child, _FUNCTION_LIKE)
        ]
        return max(child_depths, default=0)

    return depth(node)


@dataclass
class ASTMetrics:
    functions: int
    lines_of_code: int
    max_arguments: int
    max_nesting_depth: int
    cyclomatic_complexity: int
    num_loops: int
    branches: int
    function_calls: int

    def as_dict(self) -> dict:
        return asdict(self)


def _max_nesting_depth_anywhere(tree: ast.AST) -> int:
    # max_nesting_depth() on the Module node directly would discard top-level
    # functions with nothing to replace them, so measure each function on its
    # own plus module-level control flow, and take the max.
    function_defs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    depths = [max_nesting_depth(fn) for fn in function_defs]
    depths.append(max_nesting_depth(tree))
    return max(depths, default=0)


def _cyclomatic_complexity(tree: ast.AST) -> int:
    """Approximate McCabe complexity: baseline 1 + one per decision point."""
    complexity = 1
    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler)):
            complexity += 1
        elif isinstance(node, ast.BoolOp):
            complexity += len(node.values) - 1
        elif isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            complexity += sum(len(gen.ifs) for gen in node.generators)
    return complexity


def compute_metrics(source_code: str) -> Optional[ASTMetrics]:
    """Returns None on SyntaxError instead of raising -- callers treat that as "unavailable"."""
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return None

    function_defs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]

    return ASTMetrics(
        functions=len(function_defs),
        lines_of_code=len([line for line in source_code.splitlines() if line.strip()]),
        max_arguments=max((len(f.args.args) for f in function_defs), default=0),
        max_nesting_depth=_max_nesting_depth_anywhere(tree),
        cyclomatic_complexity=_cyclomatic_complexity(tree),
        num_loops=sum(1 for n in ast.walk(tree) if isinstance(n, (ast.For, ast.AsyncFor, ast.While))),
        branches=sum(1 for n in ast.walk(tree) if isinstance(n, (ast.If, ast.ExceptHandler))),
        function_calls=sum(1 for n in ast.walk(tree) if isinstance(n, ast.Call)),
    )
