"""
Deterministic, AST-derived static-analysis metrics -- no LLM involved, used to
give reviewers objective context (and a before/after comparison for a
refactor) alongside the AI-generated explanation.
"""
import ast
from dataclasses import dataclass, asdict
from typing import Optional

_NESTING_BOUNDARY_NODES = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith)
_FUNCTION_LIKE = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)


def max_nesting_depth(node: ast.AST) -> int:
    """
    Deepest nesting of control-flow blocks within `node`, not descending into
    nested function/lambda/class definitions -- so a deeply-nested closure
    doesn't inflate the nesting depth attributed to its containing function.
    """
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
    """
    Max nesting depth across the whole file. max_nesting_depth() deliberately
    stops at function/lambda/class boundaries (so a nested closure's depth
    isn't attributed to its enclosing function) -- called directly on the
    Module node, that same exclusion would incorrectly discard every
    top-level function body with nothing to replace it. So: measure each
    function's own nesting independently, plus whatever nesting exists at
    true module level outside any function, and take the max of all of it.
    """
    function_defs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    depths = [max_nesting_depth(fn) for fn in function_defs]
    depths.append(max_nesting_depth(tree))  # module-level control flow outside any function
    return max(depths, default=0)


def _cyclomatic_complexity(tree: ast.AST) -> int:
    """
    Approximate McCabe cyclomatic complexity: 1 (baseline path) plus one per
    decision point -- if/elif, for, while, except handler, each boolean
    operand beyond the first (and/or short-circuiting), and each comprehension
    'if' filter.
    """
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
    """
    Computes metrics for a whole source file. Returns None if the source
    doesn't parse, rather than raising -- callers should treat that as
    "metrics unavailable" (e.g. a failed refactor's output may not be valid
    Python at all).
    """
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
