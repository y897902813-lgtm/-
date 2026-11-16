from __future__ import annotations

import ast
import math
import operator
import re
from collections.abc import Mapping


class ExpressionError(ValueError):
    pass


_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCTIONS = {
    "abs": abs,
    "min": min,
    "max": max,
    "round": round,
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "radians": math.radians,
    "degrees": math.degrees,
}
_CONSTANTS = {"pi": math.pi, "e": math.e}


def _safe_eval_node(node: ast.AST, names: Mapping[str, float]) -> float:
    if isinstance(node, ast.Expression):
        return _safe_eval_node(node.body, names)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id in names:
            return float(names[node.id])
        if node.id in _CONSTANTS:
            return float(_CONSTANTS[node.id])
        raise ExpressionError(f"unknown variable: {node.id}")
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        return float(_BIN_OPS[type(node.op)](_safe_eval_node(node.left, names), _safe_eval_node(node.right, names)))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return float(_UNARY_OPS[type(node.op)](_safe_eval_node(node.operand, names)))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCTIONS:
        if node.keywords:
            raise ExpressionError("keyword arguments are not allowed")
        args = [_safe_eval_node(arg, names) for arg in node.args]
        return float(_FUNCTIONS[node.func.id](*args))
    raise ExpressionError(f"unsupported expression element: {type(node).__name__}")


def evaluate(expression: object, variables: Mapping[str, float] | None = None) -> float:
    if isinstance(expression, bool):
        raise ExpressionError("boolean is not a numeric expression")
    if isinstance(expression, (int, float)):
        value = float(expression)
        if not math.isfinite(value):
            raise ExpressionError("value must be finite")
        return value
    text = str(expression).strip()
    if not text:
        raise ExpressionError("expression is empty")
    variables = variables or {}
    aliases: dict[str, float] = {}
    rewritten = text
    for index, name in enumerate(sorted(variables, key=len, reverse=True)):
        alias = f"__v{index}"
        # Slash-qualified drive variables (``drive/duration1``) must be matched
        # as complete path-like tokens, while a plain custom variable after a
        # division operator (``40/tran``) must still be recognized.  Treating
        # every adjacent slash as part of an identifier made those two cases
        # indistinguishable and produced false ``unknown variable`` failures.
        if "/" in name or "." in name:
            pattern = rf"(?<![\w/]){re.escape(name)}(?![\w/])"
        else:
            pattern = rf"(?<!\w){re.escape(name)}(?!\w)"
        updated, count = re.subn(pattern, alias, rewritten)
        if count:
            aliases[alias] = float(variables[name])
            rewritten = updated
    try:
        tree = ast.parse(rewritten, mode="eval")
        value = _safe_eval_node(tree, aliases)
    except (SyntaxError, ZeroDivisionError, OverflowError, ValueError) as exc:
        if isinstance(exc, ExpressionError):
            raise
        raise ExpressionError(f"invalid expression '{text}': {exc}") from exc
    if not math.isfinite(value):
        raise ExpressionError(f"expression '{text}' produced a non-finite value")
    return value


def resolve_variables(raw: Mapping[str, object], seed: Mapping[str, float] | None = None) -> dict[str, float]:
    resolved = dict(seed or {})
    pending = dict(raw)
    errors: dict[str, str] = {}
    while pending:
        progress = False
        for name, expression in list(pending.items()):
            try:
                resolved[name] = evaluate(expression, resolved)
            except ExpressionError as exc:
                errors[name] = str(exc)
                continue
            del pending[name]
            errors.pop(name, None)
            progress = True
        if not progress:
            details = "; ".join(f"{name}: {errors.get(name, 'unresolved dependency')}" for name in pending)
            raise ExpressionError(f"cyclic or unresolved variables: {details}")
    return resolved
