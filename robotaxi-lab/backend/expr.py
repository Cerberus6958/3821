"""Safe evaluation of user-written heuristic formulas.

A formula is one or more comma-separated arithmetic expressions, compared
lexicographically (the second breaks ties in the first, and so on). Only a small
whitelist of syntax is accepted: numbers, the documented variable names,
arithmetic, comparisons, `and`/`or`/`not`, `a if cond else b`, and a few math
functions. Anything else (attribute access, indexing, strings, lambdas, imports)
is rejected before the formula is compiled.
"""

from __future__ import annotations

import ast
import math
from typing import Callable, Dict, Iterable, Tuple

FUNCTIONS = {
    "min": min,
    "max": max,
    "abs": abs,
    "sqrt": math.sqrt,
    "log": lambda x: math.log(x) if x > 0 else float("-inf"),
    "floor": math.floor,
    "ceil": math.ceil,
}

_ALLOWED = (
    ast.Expression, ast.Tuple, ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.IfExp,
    ast.Name, ast.Load, ast.Constant, ast.Call,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.USub, ast.UAdd, ast.Not, ast.And, ast.Or,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
)


class FormulaError(ValueError):
    pass


def compile_formula(text: str, variables: Iterable[str]) -> Callable[[Dict[str, float]], Tuple[float, ...]]:
    """Validate `text` and return a function mapping a variable dict to a key tuple."""
    allowed_names = set(variables)
    src = (text or "").strip()
    if not src:
        raise FormulaError("Enter a formula, for example: wait")
    if len(src) > 400:
        raise FormulaError("Formulas are limited to 400 characters.")
    try:
        tree = ast.parse(src, mode="eval")
    except SyntaxError as exc:
        raise FormulaError("Syntax error: check brackets, commas and operators.") from None

    call_funcs = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in FUNCTIONS and id(node) not in call_funcs:
            raise FormulaError(f"'{node.id}' is a function, so it needs brackets, e.g. {node.id}(a, b).")
        if not isinstance(node, _ALLOWED):
            raise FormulaError(f"'{type(node).__name__}' is not allowed in a formula.")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float)) or \
                isinstance(node, ast.Constant) and isinstance(node.value, bool):
            raise FormulaError("Only numbers can appear as constants.")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS:
                raise FormulaError("Unknown function. Available: " + ", ".join(sorted(FUNCTIONS)) + ".")
            if node.keywords:
                raise FormulaError("Functions take positional arguments only.")
        if isinstance(node, ast.Name) and node.id not in allowed_names and node.id not in FUNCTIONS:
            raise FormulaError(f"Unknown variable '{node.id}'.")
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            right = node.right
            if not (isinstance(right, ast.Constant) and abs(right.value) <= 8):
                raise FormulaError("Powers are limited to constant exponents between -8 and 8.")

    body = tree.body
    parts = body.elts if isinstance(body, ast.Tuple) else [body]
    if not parts:
        raise FormulaError("Enter at least one expression.")
    if len(parts) > 6:
        raise FormulaError("Use at most 6 comma-separated tie-break expressions.")

    wrapped = ast.Expression(body=ast.Tuple(elts=parts, ctx=ast.Load()))
    code = compile(ast.fix_missing_locations(wrapped), "<formula>", "eval")
    globals_ = {"__builtins__": {}, **FUNCTIONS}

    def evaluate(env: Dict[str, float]) -> Tuple[float, ...]:
        try:
            out = eval(code, globals_, env)  # noqa: S307 - AST whitelisted above, no builtins
        except ZeroDivisionError:
            raise FormulaError("Division by zero while evaluating the formula.") from None
        except (OverflowError, ValueError) as exc:
            raise FormulaError(f"Maths error while evaluating the formula: {exc}.") from None
        return tuple(float(v) for v in out)

    return evaluate
