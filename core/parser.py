import ast
import json
from pathlib import Path
from typing import List, Dict, Any
from .schemas import CodeSmell

class AntiPatternVisitor(ast.NodeVisitor):
    """
    An AST visitor that detects both built-in and custom-defined code smells.
    """
    def __init__(self, source_code: str, file_name: str, config: Dict[str, Any]):
        self.file_name = file_name
        self.source_lines = source_code.splitlines()
        self.smells: List[CodeSmell] = []
        self.config = config.get("rules", {})
        self.custom_rules = self.config.get("custom_rules", [])

    def _get_node_code(self, node: ast.AST) -> str:
        """Extracts the raw source code for a given AST node."""
        return ast.get_source_segment(
            "\n".join(self.source_lines), node
        )

    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Checks for long functions and functions with too many arguments."""
        # Built-in rule: function length
        max_len = self.config.get("max_function_length", 50)
        if (node.end_lineno - node.lineno) > max_len:
            self.smells.append(CodeSmell(
                issue_type="Long Function",
                target_name=node.name,
                raw_code=self._get_node_code(node),
                line_number=node.lineno,
                file_name=self.file_name
            ))
        
        # Built-in rule: too many arguments
        max_args = self.config.get("max_function_args", 5)
        if len(node.args.args) > max_args:
            self.smells.append(CodeSmell(
                issue_type="Too Many Arguments",
                target_name=node.name,
                raw_code=self._get_node_code(node),
                line_number=node.lineno,
                file_name=self.file_name
            ))
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        """Checks for bare 'except:' clauses."""
        if node.type is None:
            self.smells.append(CodeSmell(
                issue_type="Bare Except",
                target_name="except block",
                raw_code=self._get_node_code(node),
                line_number=node.lineno,
                file_name=self.file_name
            ))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        """Checks for disallowed function calls based on custom rules."""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr
        else:
            func_name = "unknown"

        for rule in self.custom_rules:
            if rule.get("type") == "disallowed_call" and rule.get("pattern") == func_name:
                self.smells.append(CodeSmell(
                    issue_type=rule.get("message", "Disallowed function call"),
                    target_name=func_name,
                    raw_code=self._get_node_code(node),
                    line_number=node.lineno,
                    file_name=self.file_name
                ))
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import):
        """Checks for disallowed 'import <module>' statements."""
        for alias in node.names:
            module_name = alias.name
            for rule in self.custom_rules:
                if rule.get("type") == "disallowed_import" and rule.get("pattern") in module_name:
                    self.smells.append(CodeSmell(
                        issue_type=rule.get("message", "Disallowed import"),
                        target_name=module_name,
                        raw_code=self._get_node_code(node),
                        line_number=node.lineno,
                        file_name=self.file_name
                    ))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        """Checks for disallowed 'from <module> import ...' statements."""
        module_name = node.module or ""
        for rule in self.custom_rules:
            if rule.get("type") == "disallowed_import_from" and rule.get("pattern") in module_name:
                self.smells.append(CodeSmell(
                    issue_type=rule.get("message", "Disallowed 'from' import"),
                    target_name=module_name,
                    raw_code=self._get_node_code(node),
                    line_number=node.lineno,
                    file_name=self.file_name
                ))
        self.generic_visit(node)

def analyze_source_code(source_code: str, file_name: str, config: Dict[str, Any]) -> List[CodeSmell]:
    """
    Parses source code into an AST and uses the AntiPatternVisitor to find smells.
    """
    try:
        tree = ast.parse(source_code)
        visitor = AntiPatternVisitor(source_code, file_name, config)
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
    return {
        "rules": {
            "max_function_args": 5,
            "max_function_length": 50,
            "custom_rules": []
        }
    }
