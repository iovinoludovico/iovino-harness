"""Typed expressions over the domain metamodel (guards, conditions and derivations of `behavior.yaml`).

A small OCL/EOL-like language, read in the context of an instance of a class (`self`, optional):

    dataComplete
    reason.compensationType = hourly and hours > 0
    invitationFunds.amount.sum() = totalAmount
    if compensationType = hourly then round(hours * hourlyRate, 2) else coalesce(flatAmount, 0)

Paths navigate attributes and single-valued references; through a many-valued reference the rest of the
path is a collection (one level), closed by `.size()`, `.sum()`, `.isEmpty()` or `.notEmpty()`. `.isSet()`
and `.isEmpty()` test a single value. Literals: numbers, 'strings', true/false and the bare literals of the
enum on the other side of a comparison. Operators: `+ - * /` (a date minus a date is a number of days),
`= <> < <= > >=`, `in [a, b]`, `and or not`, `if c then a else b`, `round(x[, n])`, `coalesce(a, b, …)`.

`parse()` builds the tree, `typecheck()` types it against the metamodel (and reports the first problem with
its position), `check()` does both and can require a type. `to_sql()` writes the typed tree as a PostgreSQL
expression on a row of the class, following the storage mapping of the metamodel. The tree is plain dicts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from . import core as M
from . import ecore as E

NUMERIC = {"int", "number", "money"}
TEXTUAL = {"string", "text", "email", "url"}
TEMPORAL = {"date", "datetime"}
BOOL = "bool"
COLLECTION = "collection:"       # collection:<type>
CLASS = "class:"                 # class:<name>
ENUM = "enum:"                   # enum:<name>  (enum:@<var> for a variable with a fixed set of names)
CALLS = {"isSet", "isEmpty", "notEmpty", "size", "sum"}
FUNCTIONS = {"round": (1, 2), "coalesce": (2, 99)}

_TOKEN = re.compile(r"""
    (?P<ws>\s+)
  | (?P<num>\d+(?:\.\d+)?)
  | (?P<str>'(?:[^'\\]|\\.)*')
  | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<op><>|<=|>=|=|<|>|\+|-|\*|/)
  | (?P<punct>[().,\[\]])
""", re.VERBOSE)
KEYWORDS = {"and", "or", "not", "in", "true", "false", "self", "if", "then", "else"}
CMP_OPS = {"=", "<>", "<", "<=", ">", ">="}


class ExprError(Exception):
    def __init__(self, msg: str, pos: int | None = None, text: str | None = None):
        super().__init__(msg)
        self.msg, self.pos, self.text = msg, pos, text

    def __str__(self) -> str:
        if self.pos is None or self.text is None:
            return self.msg
        return f"{self.msg} (at {self.pos + 1}: `{self.text[self.pos:self.pos + 20]}…`)".replace("…`", "`")


def type_name(t: str) -> str:
    """How a type is shown in messages."""
    if t.startswith(COLLECTION):
        return f"collection of {type_name(t[len(COLLECTION):])}"
    if t.startswith(CLASS):
        return t[len(CLASS):]
    if t.startswith(ENUM):
        return "one of the names" if t.startswith(ENUM + "@") else f"enum {t[len(ENUM):]}"
    return t


def feature_type(a_or_r: dict[str, Any], e: dict[str, Any], is_ref: bool) -> str:
    t = str(a_or_r.get("type"))
    if is_ref:
        base = CLASS + (E.resolve_type(e, t) or t)
    elif t in e["enums"]:
        base = ENUM + t
    else:
        base = E.DATATYPES.get(t, "string")
    return COLLECTION + base if a_or_r.get("upper", 1) != 1 else base


# --------------------------------------------------------------------------- #
# Tokens and parser
# --------------------------------------------------------------------------- #
@dataclass
class Tok:
    kind: str
    value: str
    pos: int


def tokenize(text: str) -> list[Tok]:
    out: list[Tok] = []
    i = 0
    while i < len(text):
        m = _TOKEN.match(text, i)
        if not m:
            raise ExprError(f"unexpected character {text[i]!r}", i, text)
        kind = m.lastgroup or ""
        if kind != "ws":
            v = m.group(kind)
            if kind == "ident" and v in KEYWORDS:
                kind = "kw"
            out.append(Tok(kind, v, i))
        i = m.end()
    out.append(Tok("eof", "", len(text)))
    return out


class _Parser:
    def __init__(self, text: str):
        self.text = text
        self.toks = tokenize(text)
        self.i = 0

    @property
    def cur(self) -> Tok:
        return self.toks[self.i]

    def take(self, kind: str | None = None, value: str | None = None) -> Tok:
        t = self.cur
        if (kind and t.kind != kind) or (value is not None and t.value != value):
            want = repr(value) if value is not None else kind
            raise ExprError(f"expected {want}, found {t.value!r}" if t.kind != "eof" else f"expected {want}", t.pos, self.text)
        self.i += 1
        return t

    def at(self, kind: str, value: str | None = None) -> bool:
        return self.cur.kind == kind and (value is None or self.cur.value == value)

    def parse(self) -> dict[str, Any]:
        node = self.p_expr()
        if self.cur.kind != "eof":
            raise ExprError(f"unexpected {self.cur.value!r}", self.cur.pos, self.text)
        return node

    def p_expr(self) -> dict[str, Any]:
        if self.at("kw", "if"):
            t = self.take()
            c = self.p_expr()
            self.take("kw", "then")
            a = self.p_expr()
            self.take("kw", "else")
            b = self.p_expr()
            return {"k": "if", "c": c, "a": a, "b": b, "pos": t.pos}
        return self.p_or()

    def p_or(self) -> dict[str, Any]:
        items = [self.p_and()]
        while self.at("kw", "or"):
            self.take()
            items.append(self.p_and())
        return items[0] if len(items) == 1 else {"k": "or", "items": items, "pos": items[0]["pos"]}

    def p_and(self) -> dict[str, Any]:
        items = [self.p_not()]
        while self.at("kw", "and"):
            self.take()
            items.append(self.p_not())
        return items[0] if len(items) == 1 else {"k": "and", "items": items, "pos": items[0]["pos"]}

    def p_not(self) -> dict[str, Any]:
        if self.at("kw", "not"):
            t = self.take()
            return {"k": "not", "x": self.p_not(), "pos": t.pos}
        return self.p_cmp()

    def p_cmp(self) -> dict[str, Any]:
        left = self.p_add()
        if self.at("op") and self.cur.value in CMP_OPS:
            op = self.take()
            right = self.p_add()
            return {"k": "cmp", "op": op.value, "l": left, "r": right, "pos": op.pos}
        if self.at("kw", "in"):
            t = self.take()
            self.take("punct", "[")
            items = []
            if not self.at("punct", "]"):
                items.append(self.p_add())
                while self.at("punct", ","):
                    self.take()
                    items.append(self.p_add())
            self.take("punct", "]")
            if not items:
                raise ExprError("empty list after in", t.pos, self.text)
            return {"k": "in", "x": left, "items": items, "pos": t.pos}
        return left

    def p_add(self) -> dict[str, Any]:
        node = self.p_mul()
        while self.at("op") and self.cur.value in ("+", "-"):
            op = self.take()
            node = {"k": "arith", "op": op.value, "l": node, "r": self.p_mul(), "pos": op.pos}
        return node

    def p_mul(self) -> dict[str, Any]:
        node = self.p_unary()
        while self.at("op") and self.cur.value in ("*", "/"):
            op = self.take()
            node = {"k": "arith", "op": op.value, "l": node, "r": self.p_unary(), "pos": op.pos}
        return node

    def p_unary(self) -> dict[str, Any]:
        if self.at("op", "-"):
            t = self.take()
            x = self.p_unary()
            if x["k"] == "lit" and x["t"] in NUMERIC:
                x["v"] = -x["v"]
                return x
            return {"k": "neg", "x": x, "pos": t.pos}
        return self.p_primary()

    def p_primary(self) -> dict[str, Any]:
        t = self.cur
        if t.kind == "punct" and t.value == "(":
            self.take()
            node = self.p_expr()
            self.take("punct", ")")
            return node
        if t.kind == "num":
            self.take()
            return {"k": "lit", "t": "number" if "." in t.value else "int", "v": float(t.value) if "." in t.value else int(t.value), "pos": t.pos}
        if t.kind == "str":
            self.take()
            return {"k": "lit", "t": "string", "v": t.value[1:-1].replace("\\'", "'"), "pos": t.pos}
        if t.kind == "kw" and t.value in ("true", "false"):
            self.take()
            return {"k": "lit", "t": BOOL, "v": t.value == "true", "pos": t.pos}
        nxt = self.toks[self.i + 1] if self.i + 1 < len(self.toks) else t
        if t.kind == "ident" and t.value in FUNCTIONS and nxt.kind == "punct" and nxt.value == "(":
            return self.p_function()
        if t.kind == "ident" or (t.kind == "kw" and t.value == "self"):
            return self.p_path()
        raise ExprError(f"unexpected {t.value!r}" if t.kind != "eof" else "unexpected end of expression", t.pos, self.text)

    def p_function(self) -> dict[str, Any]:
        name = self.take("ident")
        self.take("punct", "(")
        args = [self.p_expr()]
        while self.at("punct", ","):
            self.take()
            args.append(self.p_expr())
        self.take("punct", ")")
        lo, hi = FUNCTIONS[name.value]
        if not lo <= len(args) <= hi:
            want = str(lo) if lo == hi else (f"{lo} to {hi}" if hi < 99 else f"at least {lo}")
            raise ExprError(f"{name.value}() takes {want} argument(s), found {len(args)}", name.pos, self.text)
        return {"k": "fn", "f": name.value, "args": args, "pos": name.pos}

    def p_path(self) -> dict[str, Any]:
        start = self.cur
        segs: list[str] = []
        call: str | None = None
        if self.at("kw", "self"):
            self.take()
            if not self.at("punct", "."):
                return {"k": "path", "segs": [], "call": None, "pos": start.pos}
            self.take()
        while True:
            seg = self.take("ident")
            if self.at("punct", "("):
                self.take()
                self.take("punct", ")")
                if seg.value not in CALLS:
                    raise ExprError(f"unknown operation {seg.value}(): use {', '.join(sorted(CALLS))}", seg.pos, self.text)
                call = seg.value
                break
            segs.append(seg.value)
            if self.at("punct", "."):
                self.take()
                continue
            break
        return {"k": "path", "segs": segs, "call": call, "pos": start.pos}


def parse(text: str) -> dict[str, Any]:
    if not isinstance(text, str) or not text.strip():
        raise ExprError("empty expression")
    return _Parser(text.strip()).parse()


# --------------------------------------------------------------------------- #
# Types
# --------------------------------------------------------------------------- #
@dataclass
class Context:
    """Where an expression is read: the metamodel (expanded), the class of `self`, extra variables
    (name -> type, e.g. `transition` -> enum:@transition) and the names of those `@` sets."""
    e: dict[str, Any]
    cls: str
    variables: dict[str, str] = field(default_factory=dict)
    names: dict[str, list[str]] = field(default_factory=dict)      # "@transition" -> [keys]

    def literals(self, t: str) -> list[str] | None:
        if not t.startswith(ENUM):
            return None
        name = t[len(ENUM):]
        if name.startswith("@"):
            return self.names.get(name, [])
        spec = self.e["enums"].get(name)
        return [lit["name"] for lit in spec["literals"]] if spec else []


def _compatible(a: str, b: str) -> bool:
    if a == b:
        return True
    groups = (NUMERIC, TEXTUAL, TEMPORAL)
    return any(a in g and b in g for g in groups)


def _navigate(ctx: Context, node: dict[str, Any], text: str) -> str:
    """Type of a path; annotates the node with `ref` ([class, feature, ...]) and `t`."""
    segs: list[str] = node["segs"]
    if not segs and node["call"] is None:
        node["t"] = CLASS + ctx.cls
        node["ref"] = [ctx.cls]
        return node["t"]
    if segs and segs[0] in ctx.variables and len(segs) == 1 and node["call"] is None:
        node["t"] = ctx.variables[segs[0]]
        node["ref"] = ["@" + segs[0]]
        return node["t"]
    t = CLASS + ctx.cls
    many = False
    ref = [ctx.cls]
    for i, seg in enumerate(segs):
        base = t[len(COLLECTION):] if t.startswith(COLLECTION) else t
        if not base.startswith(CLASS):
            raise ExprError(f"'{'.'.join(segs[:i])}' is {type_name(t)}: it has no feature '{seg}'", node["pos"], text)
        cname = base[len(CLASS):]
        if cname in E.BUILTIN_CLASSES:
            if seg == "email" and cname == "User":
                nt = "email"
            else:
                raise ExprError(f"{cname} is built in: only 'email' can be navigated (not '{seg}')", node["pos"], text)
        else:
            attrs, refs = E.features(ctx.e, cname)
            if seg in attrs:
                nt = feature_type(attrs[seg], ctx.e, False)
            elif seg in refs:
                nt = feature_type(refs[seg], ctx.e, True)
            else:
                hint = " (a bare name is an enum literal only next to an attribute of that enum)" if i == 0 and segs == [seg] else ""
                raise ExprError(f"'{seg}' is not a feature of {cname}{hint}", node["pos"], text)
        if nt.startswith(COLLECTION):
            if many:
                raise ExprError(f"'{'.'.join(segs[:i + 1])}' is a collection of collections: navigate one many-valued "
                                "reference at most", node["pos"], text)
            many = True
            nt = nt[len(COLLECTION):]
        ref.append(seg)
        t = COLLECTION + nt if many else nt
    call = node["call"]
    if call:
        base = t[len(COLLECTION):] if t.startswith(COLLECTION) else t
        if call == "isSet":
            if many:
                raise ExprError(f"isSet() tests a single value: '{'.'.join(segs)}' is a collection (use notEmpty())", node["pos"], text)
            if not segs:
                raise ExprError("isSet() needs a feature", node["pos"], text)
            t = BOOL
        elif call == "isEmpty":
            if not segs:
                raise ExprError("isEmpty() needs a feature", node["pos"], text)
            t = BOOL
        elif call == "notEmpty":
            if not many:
                raise ExprError(f"notEmpty() needs a collection: '{'.'.join(segs)}' is {type_name(t)} (use isSet())", node["pos"], text)
            t = BOOL
        elif call == "size":
            if not many:
                raise ExprError(f"size() needs a collection: '{'.'.join(segs)}' is {type_name(t)}", node["pos"], text)
            t = "int"
        elif call == "sum":
            if not many or base not in NUMERIC:
                raise ExprError(f"sum() needs a collection of numbers: '{'.'.join(segs)}' is {type_name(t)}", node["pos"], text)
            t = "number"
    node["t"] = t
    node["ref"] = ref
    return t


def _literal_for(node: dict[str, Any], other_t: str, ctx: Context, text: str) -> str | None:
    """A bare name next to an enum: the literal of that enum (typed as the enum), else None."""
    if node["k"] != "path" or node["call"] or len(node["segs"]) != 1:
        return None
    name = node["segs"][0]
    base = other_t[len(COLLECTION):] if other_t.startswith(COLLECTION) else other_t
    lits = ctx.literals(base)
    if lits is None:
        return None
    attrs, refs = E.features(ctx.e, ctx.cls) if ctx.cls in ctx.e["classes"] else ({}, {})
    if name in attrs or name in refs or name in ctx.variables:
        return None                     # a feature wins over a literal with the same name
    if name not in lits:
        raise ExprError(f"'{name}' is not a literal of {type_name(base)} ({', '.join(lits) or 'none'})", node["pos"], text)
    node.update({"k": "lit", "t": base, "v": name})
    return base


def _scalar(t: str, where: dict[str, Any], text: str, what: str) -> None:
    if t.startswith(COLLECTION):
        raise ExprError(f"{what} a collection: use size(), sum(), isEmpty() or notEmpty()", where["pos"], text)
    if t.startswith(CLASS):
        raise ExprError(f"{what} a reference: use isSet() or navigate to an attribute", where["pos"], text)


def typecheck(node: dict[str, Any], ctx: Context, text: str = "") -> str:
    """Type of the expression; annotates every node with `t`. Raises ExprError on the first problem."""
    k = node["k"]
    if k == "lit":
        return node["t"]
    if k == "path":
        return _navigate(ctx, node, text)
    if k in ("and", "or"):
        for x in node["items"]:
            t = typecheck(x, ctx, text)
            if t != BOOL:
                raise ExprError(f"'{k}' needs booleans, found {type_name(t)}", x["pos"], text)
        node["t"] = BOOL
        return BOOL
    if k == "not":
        t = typecheck(node["x"], ctx, text)
        if t != BOOL:
            raise ExprError(f"'not' needs a boolean, found {type_name(t)}", node["x"]["pos"], text)
        node["t"] = BOOL
        return BOOL
    if k == "cmp":
        lt = _side(node["l"], node["r"], ctx, text)
        rt = _side(node["r"], node["l"], ctx, text)
        _scalar(lt, node, text, "cannot compare")
        _scalar(rt, node, text, "cannot compare")
        if not _compatible(lt, rt):
            raise ExprError(f"cannot compare {type_name(lt)} with {type_name(rt)}", node["pos"], text)
        if node["op"] in ("<", "<=", ">", ">=") and lt not in NUMERIC and lt not in TEMPORAL:
            raise ExprError(f"'{node['op']}' needs numbers or dates, found {type_name(lt)}", node["pos"], text)
        node["t"] = BOOL
        return BOOL
    if k == "in":
        xt = typecheck(node["x"], ctx, text)
        _scalar(xt, node, text, "'in' tests a single value, not")
        for item in node["items"]:
            it = _literal_for(item, xt, ctx, text) or typecheck(item, ctx, text)
            if not _compatible(xt, it):
                raise ExprError(f"cannot compare {type_name(xt)} with {type_name(it)}", item["pos"], text)
        node["t"] = BOOL
        return BOOL
    if k == "arith":
        lt, rt = typecheck(node["l"], ctx, text), typecheck(node["r"], ctx, text)
        _scalar(lt, node, text, f"'{node['op']}' cannot take")
        _scalar(rt, node, text, f"'{node['op']}' cannot take")
        if node["op"] == "-" and lt in TEMPORAL and rt in TEMPORAL:
            node["t"] = "int"                                # days between two dates
            return "int"
        if lt not in NUMERIC or rt not in NUMERIC:
            raise ExprError(f"'{node['op']}' needs numbers, found {type_name(lt)} and {type_name(rt)}", node["pos"], text)
        node["t"] = "int" if lt == rt == "int" and node["op"] != "/" else "number"
        return node["t"]
    if k == "neg":
        t = typecheck(node["x"], ctx, text)
        if t not in NUMERIC:
            raise ExprError(f"'-' needs a number, found {type_name(t)}", node["pos"], text)
        node["t"] = t
        return t
    if k == "fn":
        ts = [typecheck(a, ctx, text) for a in node["args"]]
        if node["f"] == "round":
            if ts[0] not in NUMERIC or (len(ts) > 1 and ts[1] != "int"):
                raise ExprError("round() takes a number and an optional integer number of decimals", node["pos"], text)
            node["t"] = "number"
        else:                                                # coalesce: the first value that is set
            for a, t in zip(node["args"], ts):
                _scalar(t, a, text, "coalesce() cannot take")
                if not _compatible(ts[0], t):
                    raise ExprError(f"coalesce() mixes {type_name(ts[0])} and {type_name(t)}", a["pos"], text)
            node["t"] = ts[0]
        return node["t"]
    if k == "if":
        ct = typecheck(node["c"], ctx, text)
        if ct != BOOL:
            raise ExprError(f"'if' needs a boolean condition, found {type_name(ct)}", node["c"]["pos"], text)
        at = _side(node["a"], node["b"], ctx, text)
        bt = _side(node["b"], node["a"], ctx, text)
        _scalar(at, node["a"], text, "'if' cannot give")
        _scalar(bt, node["b"], text, "'if' cannot give")
        if not _compatible(at, bt):
            raise ExprError(f"'then' gives {type_name(at)}, 'else' gives {type_name(bt)}", node["pos"], text)
        node["t"] = at if at == bt or at not in NUMERIC else "number"
        return node["t"]
    raise ExprError(f"unknown node {k}")


def _side(node: dict[str, Any], other: dict[str, Any], ctx: Context, text: str) -> str:
    """One side of a comparison (or of an if): a bare name is read as a literal of the enum on the other side."""
    if node["k"] == "path" and not node["call"] and len(node["segs"]) == 1:
        try:
            ot: str | None = typecheck(other, ctx, text)
        except ExprError:
            ot = None                   # the other side may be the literal: typed below from this side
        if ot is not None:
            lit = _literal_for(node, ot, ctx, text)
            if lit:
                return lit
    return typecheck(node, ctx, text)


def check(text: str, ctx: Context, expect: str | None = None) -> tuple[dict[str, Any], str]:
    """Parse and type an expression; `expect` requires that type (BOOL for guards, the attribute's for derivations)."""
    node = parse(text)
    t = typecheck(node, ctx, text.strip())
    if expect is not None and not _compatible(t, expect):
        raise ExprError(f"expected {type_name(expect)}, found {type_name(t)}", node["pos"], text.strip())
    return node, t


def children(node: dict[str, Any]) -> list[dict[str, Any]]:
    out = [node[k] for k in ("x", "l", "r", "c", "a", "b") if isinstance(node.get(k), dict)]
    return out + list(node.get("items", [])) + list(node.get("args", []))


def features_used(node: dict[str, Any]) -> list[tuple[str, ...]]:
    """Every navigation of a typed tree as (class, feature, feature…), in order of appearance."""
    out: list[tuple[str, ...]] = []
    if node["k"] == "path" and node.get("ref") and len(node["ref"]) > 1 and not node["ref"][0].startswith("@"):
        out.append(tuple(node["ref"]))
    for c in children(node):
        out += features_used(c)
    return out


def to_text(node: dict[str, Any]) -> str:
    """The expression back as text (normalized spacing)."""
    k = node["k"]
    if k == "lit":
        v = node["v"]
        if node["t"] == BOOL:
            return "true" if v else "false"
        if node["t"] == "string":
            return "'" + str(v).replace("'", "\\'") + "'"
        return str(v)
    if k == "path":
        s = ".".join(node["segs"]) or "self"
        return f"{s}.{node['call']}()" if node["call"] else s
    if k in ("and", "or"):
        return f" {k} ".join(_wrap(x, k) for x in node["items"])
    if k == "not":
        return "not " + _wrap(node["x"], "not")
    if k == "cmp":
        return f"{_wrap(node['l'], 'cmp')} {node['op']} {_wrap(node['r'], 'cmp')}"
    if k == "in":
        return f"{_wrap(node['x'], 'in')} in [{', '.join(to_text(i) for i in node['items'])}]"
    if k == "arith":
        return f"{_wrap(node['l'], node['op'])} {node['op']} {_wrap(node['r'], node['op'], right=True)}"
    if k == "neg":
        return "-" + _wrap(node["x"], "*")
    if k == "fn":
        return f"{node['f']}({', '.join(to_text(a) for a in node['args'])})"
    if k == "if":
        return f"if {to_text(node['c'])} then {to_text(node['a'])} else {to_text(node['b'])}"
    return "?"


_PREC = {"or": 1, "and": 2, "not": 3, "cmp": 4, "in": 4, "+": 5, "-": 5, "*": 6, "/": 6}


def _wrap(node: dict[str, Any], outer: str, right: bool = False) -> str:
    s = to_text(node)
    inner = node["k"]
    if inner == "if" or (outer == "not" and inner in ("cmp", "in", "and", "or")):
        return f"({s})"
    ip = _PREC.get(node["op"] if inner == "arith" else inner)
    op = _PREC.get(outer)
    if ip is None or op is None:
        return s
    if ip < op or (ip == op and (right or inner in ("cmp", "in"))):
        return f"({s})"
    return s


# --------------------------------------------------------------------------- #
# SQL
# --------------------------------------------------------------------------- #
@dataclass
class SqlContext:
    """A typed expression as PostgreSQL on one row (`alias`) of the class, with the metamodel's storage mapping.
    `variables` gives the SQL of each variable (`transition` -> "(p_extra -> 'transition' ->> 'key')")."""
    e: dict[str, Any]
    cls: str
    alias: str = "r"
    schema: str = "public"
    variables: dict[str, str] = field(default_factory=dict)
    _n: int = 0

    def fresh(self) -> str:
        self._n += 1
        return f"x{self._n}"

    def table(self, cname: str) -> str:
        if cname in E.BUILTIN_CLASSES:
            return f"{self.schema}.profiles"
        c = self.e["classes"][cname]
        return f"{self.schema}.{c.get('table') or E.default_table(cname, self.e['language'])}"


def ref_store(e: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    """(class, reference) -> how its target rows are reached from a row of the class:
    `fk` (column on this table), `inverse` (column on the target table), `join` (a join table)."""
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for col in E.reference_columns(e):
        holder, fname = col["from"]
        if col["many"]:
            table = f"{(e['classes'][holder].get('table') or E.default_table(holder, e['language']))}_{col['field']}"
            jt = {"join": col["spec"].get("join_table") or table, "here": f"{M.snake(holder)}_id",
                  "there": f"{col['field']}_id" if col["target"] == holder else f"{M.snake(col['target'])}_id"}
            out[(holder, fname)] = {"kind": "join", "target": col["target"], **jt}
            if col["inverse"]:
                icls, iref = col["inverse"]
                out[(icls, iref)] = {"kind": "join", "target": holder, "join": jt["join"], "here": jt["there"], "there": jt["here"]}
            continue
        if col["holder"] == holder:                               # the foreign key is on this class
            out[(holder, fname)] = {"kind": "fk", "target": col["target"], "column": col["field"]}
            if col["inverse"]:
                icls, iref = col["inverse"]
                out[(icls, iref)] = {"kind": "inverse", "target": holder, "column": col["field"]}
        else:                                                     # containment without opposite: the column is on the part
            out[(holder, fname)] = {"kind": "inverse", "target": col["holder"], "column": col["field"]}
    return out


def _sql_literal(node: dict[str, Any]) -> str:
    v = node["v"]
    if node["t"] == BOOL:
        return "true" if v else "false"
    if node["t"].startswith(ENUM):
        return "'" + (str(v) if node["t"].startswith(ENUM + "@") else E.literal_key(str(v))) + "'"
    if node["t"] in NUMERIC:
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def _is_set(value: str, t: str) -> str:
    return f"nullif(trim({value}), '') is not null" if t in TEXTUAL else f"{value} is not null"


def _path_sql(node: dict[str, Any], ctx: SqlContext) -> str:
    segs: list[str] = node["segs"]
    call = node["call"]
    if segs and node.get("ref") and node["ref"][0].startswith("@"):
        if segs[0] not in ctx.variables:
            raise ExprError(f"no SQL for the variable '{segs[0]}' here", node["pos"])
        return ctx.variables[segs[0]]
    store = ref_store(ctx.e)
    e = ctx.e
    cname = ctx.cls
    alias = ctx.alias                    # alias of the current row(s)
    frm: list[str] = []                  # FROM and JOIN clauses of the subquery (empty: still on the row itself)
    where: list[str] = []
    many = False
    value: str | None = None
    value_t: str | None = None
    last_fk: str | None = None           # `alias.column` of the last hop when it is a foreign key on the row before
    for i, seg in enumerate(segs):
        if cname in E.BUILTIN_CLASSES:                       # User: only email
            value, value_t = f"{alias}.email", "email"
            continue
        attrs, refs = E.features(e, cname)
        if seg in attrs:
            value = f"{alias}.{E.field_key(seg, attrs[seg])}"
            value_t = feature_type(attrs[seg], e, False)
            continue
        how = store.get((cname, seg))
        if how is None:
            raise ExprError(f"no storage for {cname}.{seg}", node["pos"])
        target = how["target"]
        x = ctx.fresh()
        many = many or refs[seg]["upper"] != 1
        if how["kind"] == "fk":
            cond = f"{x}.id = {alias}.{how['column']}"
            last_fk = f"{alias}.{how['column']}"
            tables = [f"{ctx.table(target)} {x}"]
        elif how["kind"] == "inverse":
            cond = f"{x}.{how['column']} = {alias}.id"
            last_fk = None
            tables = [f"{ctx.table(target)} {x}"]
        else:
            j, x = x, ctx.fresh()                        # the join table first, then the target rows
            cond = f"{j}.{how['here']} = {alias}.id"
            last_fk = None
            tables = [f"{ctx.schema}.{how['join']} {j}", f"join {ctx.table(target)} {x} on {x}.id = {j}.{how['there']}"]
        if not frm:
            frm, where = tables, [cond]
        else:
            frm.append(f"join {tables[0]} on {cond}" if len(tables) == 1
                       else f"join {tables[0]} on {cond} {tables[1]}")
        alias, cname = x, target
    sub = f"from {' '.join(frm)} where {' and '.join(where)}" if frm else ""
    if call is None:
        if value is None:
            raise ExprError("a reference has no SQL value: navigate to an attribute or use isSet()", node["pos"])
        return value if not frm else f"(select {value} {sub})"
    if call == "sum":
        return f"(select coalesce(sum({value}), 0) {sub})"
    if call == "size":
        return f"(select count(*) {sub})"
    if call == "notEmpty":
        return f"exists (select 1 {sub})"
    if call == "isEmpty" and many:
        return f"not exists (select 1 {sub})"
    # a single value: an attribute, or a reference (set = the row exists)
    if value is not None:
        test = _is_set(value if not frm else f"(select {value} {sub})", value_t or "")
    elif last_fk is not None and len(frm) == 1:
        test = f"{last_fk} is not null"
    else:
        test = f"exists (select 1 {sub})"
    return test if call == "isSet" else f"not ({test})"


def to_sql(node: dict[str, Any], ctx: SqlContext) -> str:
    """PostgreSQL for a typed tree. Comparisons follow SQL's null logic: wrap a boolean in coalesce(…, false)
    where a definite answer is needed."""
    k = node["k"]
    if k == "lit":
        return _sql_literal(node)
    if k == "path":
        return _path_sql(node, ctx)
    if k in ("and", "or"):
        return "(" + f" {k} ".join(to_sql(x, ctx) for x in node["items"]) + ")"
    if k == "not":
        return f"not ({to_sql(node['x'], ctx)})"
    if k == "cmp":
        return f"{to_sql(node['l'], ctx)} {node['op']} {to_sql(node['r'], ctx)}"
    if k == "in":
        return f"{to_sql(node['x'], ctx)} in ({', '.join(to_sql(i, ctx) for i in node['items'])})"
    if k == "arith":
        l, r = to_sql(node["l"], ctx), to_sql(node["r"], ctx)
        lt, rt = node["l"].get("t", ""), node["r"].get("t", "")
        if node["op"] == "-" and lt in TEMPORAL and rt in TEMPORAL:
            return f"({l}::date - {r}::date)" if "datetime" in (lt, rt) else f"({l} - {r})"
        if node["op"] == "/":
            return f"({l}::numeric / {r})"
        return f"({l} {node['op']} {r})"
    if k == "neg":
        return f"-({to_sql(node['x'], ctx)})"
    if k == "fn":
        args = [to_sql(a, ctx) for a in node["args"]]
        if node["f"] == "round":
            return f"round(({args[0]})::numeric{', ' + args[1] if len(args) > 1 else ''})"
        return f"coalesce({', '.join(args)})"
    if k == "if":
        return f"case when {to_sql(node['c'], ctx)} then {to_sql(node['a'], ctx)} else {to_sql(node['b'], ctx)} end"
    raise ExprError(f"unknown node {k}")
