"""Formula layer: parse Qlib expressions into a safe AST, canonicalise them,
measure complexity and originality, and mutate/cross them over (for the GP miner).

Why an AST and not regex: Qlib turns an expression string into Python and
calls eval(). A regex auditor cannot stop attribute access such as
`$close.__class__`, so every expression, and above all LLM output, is parsed
and checked against an explicit node whitelist before Qlib ever sees it.

Originality and complexity follow AlphaAgent (Tang et al., KDD 2025): the
largest common subtree against a reference "zoo", node counts, raw-feature
counts and free constants. This is a clean re-implementation, not copied code.
"""
from __future__ import annotations

import ast
import hashlib
import random
import re
from dataclasses import dataclass

FIELDS = ("open", "high", "low", "close", "vwap", "volume", "amount")
OPS = {
    # op name -> (min args, max args); the last int arg of rolling ops is a window
    "Ref": (2, 2), "Mean": (2, 2), "Std": (2, 2), "Var": (2, 2), "Max": (2, 2),
    "Min": (2, 2), "Sum": (2, 2), "Delta": (2, 2), "Slope": (2, 2), "Rsquare": (2, 2),
    "Resi": (2, 2), "Rank": (2, 2), "Skew": (2, 2), "Kurt": (2, 2), "EMA": (2, 2),
    "WMA": (2, 2), "Med": (2, 2), "Mad": (2, 2), "IdxMax": (2, 2), "IdxMin": (2, 2),
    "Quantile": (3, 3), "Corr": (3, 3), "Cov": (3, 3),
    "Abs": (1, 1), "Log": (1, 1), "Sign": (1, 1),
    "Greater": (2, 2), "Less": (2, 2), "If": (3, 3), "Power": (2, 2),
}
ROLLING = {k for k, (lo, hi) in OPS.items() if k not in
           {"Abs", "Log", "Sign", "Greater", "Less", "If", "Power"}}
COMMUTATIVE_OPS = {"Corr", "Cov", "Greater", "Less"}
MAX_WINDOW = 260
_ALLOWED_NODES = (ast.Expression, ast.Call, ast.Name, ast.Load, ast.Constant,
                  ast.BinOp, ast.UnaryOp, ast.Add, ast.Sub, ast.Mult, ast.Div,
                  ast.USub, ast.UAdd)
_FIELD_RE = re.compile(r"\$([A-Za-z_]+)")


class ExprError(ValueError):
    pass


# ----------------------------------------------------------------------------
# parse / unparse
# ----------------------------------------------------------------------------
def _to_py(expr: str) -> str:
    return _FIELD_RE.sub(lambda m: f"F_{m.group(1)}", expr)


def _to_qlib(src: str) -> str:
    return re.sub(r"\bF_([A-Za-z_]+)", r"$\1", src)


def parse(expr: str) -> ast.Expression:
    """Parse and validate. Raises ExprError on anything outside the whitelist."""
    if not isinstance(expr, str) or not expr.strip():
        raise ExprError("empty expression")
    if len(expr) > 600:
        raise ExprError("expression too long")
    if "__" in expr or "lambda" in expr:
        raise ExprError("forbidden token")
    try:
        tree = ast.parse(_to_py(expr), mode="eval")
    except SyntaxError as e:
        raise ExprError(f"syntax error: {e.msg}") from None
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ExprError(f"forbidden syntax: {type(node).__name__}")
        if isinstance(node, ast.Name):
            if node.id.startswith("F_"):
                if node.id[2:] not in FIELDS:
                    raise ExprError(f"unknown field ${node.id[2:]}")
            elif node.id not in OPS:
                raise ExprError(f"unknown name {node.id}")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float)):
            raise ExprError("only numeric constants allowed")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in OPS:
                raise ExprError("calls must be whitelisted operators")
            if node.keywords:
                raise ExprError("keyword arguments not allowed")
            lo, hi = OPS[node.func.id]
            if not lo <= len(node.args) <= hi:
                raise ExprError(f"{node.func.id} takes {lo}-{hi} args")
            if node.func.id in ROLLING or node.func.id == "Ref":
                w = node.args[-1]
                val = _const_value(w)
                if val is None:
                    raise ExprError(f"{node.func.id} window must be a constant")
                if node.func.id == "Ref" and val < 1:
                    raise ExprError("Ref shift must be >= 1 (negative = look-ahead)")
                if node.func.id != "Ref" and val < 2:
                    raise ExprError("rolling window must be >= 2")
                if val > MAX_WINDOW:
                    raise ExprError(f"window {val} > {MAX_WINDOW}")
    return tree


def _const_value(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        v = _const_value(node.operand)
        return -v if v is not None else None
    return None


def unparse(tree: ast.AST) -> str:
    return _to_qlib(ast.unparse(tree))


def is_valid(expr: str) -> tuple[bool, str]:
    try:
        parse(expr)
        return True, "ok"
    except ExprError as e:
        return False, str(e)


# ----------------------------------------------------------------------------
# canonical form, complexity, originality
# ----------------------------------------------------------------------------
def _canon(node, constants=True) -> str:
    """Canonical string. Commutative args are sorted, so Corr(a,b) == Corr(b,a).
    With constants=False every number becomes C (structure-only)."""
    if isinstance(node, ast.Expression):
        return _canon(node.body, constants)
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Constant):
        return repr(node.value) if constants else "C"
    if isinstance(node, ast.UnaryOp):
        v = _const_value(node)
        if v is not None:
            return repr(v) if constants else "C"
        return f"neg({_canon(node.operand, constants)})"
    if isinstance(node, ast.BinOp):
        op = type(node.op).__name__
        a, b = _canon(node.left, constants), _canon(node.right, constants)
        if op in ("Add", "Mult"):
            a, b = sorted((a, b))
        return f"{op}({a},{b})"
    if isinstance(node, ast.Call):
        name = node.func.id
        args = [_canon(x, constants) for x in node.args]
        if name in COMMUTATIVE_OPS:
            n_series = len(args) - (1 if name in ("Corr", "Cov") else 0)
            args = sorted(args[:n_series]) + args[n_series:]
        return f"{name}({','.join(args)})"
    raise ExprError(f"unexpected node {type(node).__name__}")


def canonical(expr: str) -> str:
    return _canon(parse(expr))


def fingerprint(expr: str) -> str:
    return hashlib.sha1(canonical(expr).encode()).hexdigest()[:12]


def _children(node):
    if isinstance(node, ast.Expression):
        return [node.body]
    if isinstance(node, ast.BinOp):
        return [node.left, node.right]
    if isinstance(node, ast.UnaryOp):
        return [] if _const_value(node) is not None else [node.operand]
    if isinstance(node, ast.Call):
        return list(node.args)
    return []


def _subtrees(node, out):
    """Collect (structure-hash -> size) for every subtree. Returns size."""
    size = 1 + sum(_subtrees(c, out) for c in _children(node))
    if not isinstance(node, ast.Expression):
        h = _canon(node, constants=False)
        out[h] = max(out.get(h, 0), size)
    return size


@dataclass(frozen=True)
class Complexity:
    nodes: int
    depth: int
    raw_fields: int
    constants: int


def complexity(expr: str) -> Complexity:
    tree = parse(expr)
    nodes = sum(1 for n in ast.walk(tree) if isinstance(n, (ast.Call, ast.BinOp, ast.Name,
                                                               ast.Constant, ast.UnaryOp))
                and not (isinstance(n, ast.Name) and n.id in OPS))

    def depth(n):
        ch = _children(n)
        return 1 + (max(depth(c) for c in ch) if ch else 0)
    fields = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id.startswith("F_")}
    consts = sum(1 for n in ast.walk(tree) if isinstance(n, ast.Constant))
    return Complexity(nodes, depth(tree.body), len(fields), consts)


class Zoo:
    """Reference set for originality: the largest common subtree (structure
    only, constants ignored) between a candidate and any zoo member."""

    def __init__(self, exprs=()):
        self._subtrees: dict[str, int] = {}
        self.members: list[str] = []
        for e in exprs:
            self.add(e)

    def add(self, expr: str):
        try:
            _subtrees(parse(expr), self._subtrees)
            self.members.append(expr)
        except ExprError:
            pass

    def overlap(self, expr: str) -> int:
        cand: dict[str, int] = {}
        _subtrees(parse(expr), cand)
        common = [s for h, s in cand.items() if h in self._subtrees]
        return max(common, default=0)


# ----------------------------------------------------------------------------
# random generation and genetic operators (GP miner)
# ----------------------------------------------------------------------------
TERMINALS = ["$open", "$high", "$low", "$close", "$vwap", "$volume",
             "($close/Ref($close,1)-1)", "(($high-$low)/$close)", "($close/$vwap-1)",
             "Log($volume+1)"]
WINDOWS = [5, 10, 20, 40, 60]
UNARY_ROLL = ["Mean", "Std", "Max", "Min", "Slope", "Skew", "Rank", "Sum", "Delta", "EMA"]


def random_expr(rng: random.Random, depth: int = 2) -> str:
    """Random, scale-free-ish formula from a small grammar."""
    if depth <= 0:
        return rng.choice(TERMINALS)
    k = rng.random()
    a = random_expr(rng, depth - 1) if rng.random() < 0.35 else rng.choice(TERMINALS)
    b = rng.choice(TERMINALS)
    w1, w2 = rng.choice(WINDOWS), rng.choice(WINDOWS)
    if k < 0.2 and a != b:
        return f"Corr({a},{b},{w1})"
    if k < 0.4:
        return f"({a}-Mean({a},{w1}))/(Std({a},{w1})+1e-12)"
    if k < 0.6 and w1 != w2:
        op = rng.choice(["Mean", "Max", "Min", "Sum"])
        return f"{op}({a},{w1})/({op}({a},{w2})+1e-12)-1"
    if k < 0.85:
        return f"{rng.choice(UNARY_ROLL)}({a},{w1})"
    return f"{rng.choice(UNARY_ROLL)}({a},{w1})/({rng.choice(UNARY_ROLL)}({b},{w2})+1e-12)"


def _nodes_with_parent(tree):
    out = []
    for parent in ast.walk(tree):
        for field, value in ast.iter_fields(parent):
            if isinstance(value, ast.AST) and isinstance(value, (ast.Call, ast.BinOp, ast.Name)):
                if not (isinstance(value, ast.Name) and value.id in OPS):
                    out.append((parent, field, None, value))
            elif isinstance(value, list):
                for i, v in enumerate(value):
                    if isinstance(v, (ast.Call, ast.BinOp, ast.Name)):
                        out.append((parent, field, i, v))
    return out


def _replace(parent, field, idx, new):
    if idx is None:
        setattr(parent, field, new)
    else:
        getattr(parent, field)[idx] = new


def mutate(expr: str, rng: random.Random) -> str:
    """Point mutation (change a window), subtree mutation, or operator swap."""
    tree = parse(expr)
    k = rng.random()
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and n.func.id in ROLLING]
    if k < 0.35 and calls:
        c = rng.choice(calls)
        c.args[-1] = ast.Constant(rng.choice(WINDOWS))
    elif k < 0.6 and calls:
        c = rng.choice([c for c in calls if c.func.id in UNARY_ROLL] or calls)
        if c.func.id in UNARY_ROLL:
            c.func = ast.Name(rng.choice(UNARY_ROLL), ast.Load())
    else:
        spots = _nodes_with_parent(tree)
        if spots:
            parent, field, idx, _ = rng.choice(spots)
            new = ast.parse(_to_py(random_expr(rng, 1)), mode="eval").body
            _replace(parent, field, idx, new)
    out = unparse(ast.fix_missing_locations(tree))
    parse(out)
    return out


def crossover(a: str, b: str, rng: random.Random) -> str:
    """Graft a random subtree of b into a random position of a."""
    ta, tb = parse(a), parse(b)
    spots_a = _nodes_with_parent(ta)
    subs_b = [n for (_, _, _, n) in _nodes_with_parent(tb)]
    if not spots_a or not subs_b:
        return a
    parent, field, idx, _ = rng.choice(spots_a)
    _replace(parent, field, idx, rng.choice(subs_b))
    out = unparse(ast.fix_missing_locations(ta))
    parse(out)
    return out
