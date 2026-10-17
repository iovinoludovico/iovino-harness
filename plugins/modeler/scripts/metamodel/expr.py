"""Typed expressions over the domain metamodel (guards, conditions and derivations of `behavior.yaml`).

A small OCL/EOL-like language, read in the context of an instance of a class (`self`, optional):

    dataComplete
    reason.compensationType = hourly and hours > 0
    invitationFunds.amount.sum() = totalAmount
    accommodationVenue.isSet() and not (travelMethod in [agency, none])

Paths navigate attributes and single-valued references; through a many-valued reference the rest of the
path is a collection (one level), closed by `.size()`, `.sum()`, `.isEmpty()` or `.notEmpty()`. `.isSet()`
and `.isEmpty()` test a single value. Literals: numbers, 'strings', true/false and the bare literals of the
enum on the other side of a comparison. Operators: `= <> < <= > >=`, `in [a, b]`, `and or not`, parentheses.

`parse()` builds the tree, `typecheck()` types it against the metamodel (and reports the first problem with
its position); `check()` does both and can require a type. The tree is plain dicts: generators read it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from . import ecore as E

NUMERIC = {"int", "number", "money"}
TEXTUAL = {"string", "text", "email", "url"}
TEMPORAL = {"date", "datetime"}
BOOL = "bool"
COLLECTION = "collection:"       # collection:<type>
CLASS = "class:"                 # class:<name>
ENUM = "enum:"                   # enum:<name>  (enum:@<var> for a variable with a fixed set of names)
CALLS = {"isSet", "isEmpty", "notEmpty", "size", "sum"}

_TOKEN = re.compile(r"""
    (?P<ws>\s+)
  | (?P<num>\d+(?:\.\d+)?)
  | (?P<str>'(?:[^'\\]|\\.)*')
  | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<op><>|<=|>=|=|<|>)
  | (?P<punct>[().,\[\]])
""", re.VERBOSE)
KEYWORDS = {"and", "or", "not", "in", "true", "false", "self"}


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
        node = self.p_or()
        if self.cur.kind != "eof":
            raise ExprError(f"unexpected {self.cur.value!r}", self.cur.pos, self.text)
        return node

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
        left = self.p_primary()
        if self.at("op"):
            op = self.take()
            right = self.p_primary()
            return {"k": "cmp", "op": op.value, "l": left, "r": right, "pos": op.pos}
        if self.at("kw", "in"):
            t = self.take()
            self.take("punct", "[")
            items = []
            if not self.at("punct", "]"):
                items.append(self.p_primary())
                while self.at("punct", ","):
                    self.take()
                    items.append(self.p_primary())
            self.take("punct", "]")
            if not items:
                raise ExprError("empty list after in", t.pos, self.text)
            return {"k": "in", "x": left, "items": items, "pos": t.pos}
        return left

    def p_primary(self) -> dict[str, Any]:
        t = self.cur
        if t.kind == "punct" and t.value == "(":
            self.take()
            node = self.p_or()
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
        if t.kind == "ident" or (t.kind == "kw" and t.value == "self"):
            return self.p_path()
        raise ExprError(f"unexpected {t.value!r}" if t.kind != "eof" else "unexpected end of expression", t.pos, self.text)

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
        if lt.startswith(COLLECTION) or rt.startswith(COLLECTION):
            raise ExprError("a collection cannot be compared: use size(), sum(), isEmpty() or notEmpty()", node["pos"], text)
        if lt.startswith(CLASS) or rt.startswith(CLASS):
            raise ExprError("a reference cannot be compared: use isSet() or navigate to an attribute", node["pos"], text)
        if not _compatible(lt, rt):
            raise ExprError(f"cannot compare {type_name(lt)} with {type_name(rt)}", node["pos"], text)
        if node["op"] in ("<", "<=", ">", ">=") and lt not in NUMERIC and lt not in TEMPORAL:
            raise ExprError(f"'{node['op']}' needs numbers or dates, found {type_name(lt)}", node["pos"], text)
        node["t"] = BOOL
        return BOOL
    if k == "in":
        xt = typecheck(node["x"], ctx, text)
        if xt.startswith((COLLECTION, CLASS)):
            raise ExprError("'in' tests a single value", node["pos"], text)
        for item in node["items"]:
            it = _literal_for(item, xt, ctx, text) or typecheck(item, ctx, text)
            if not _compatible(xt, it):
                raise ExprError(f"cannot compare {type_name(xt)} with {type_name(it)}", item["pos"], text)
        node["t"] = BOOL
        return BOOL
    raise ExprError(f"unknown node {k}")


def _side(node: dict[str, Any], other: dict[str, Any], ctx: Context, text: str) -> str:
    """One side of a comparison: a bare name is read as a literal of the enum on the other side."""
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


def features_used(node: dict[str, Any]) -> list[tuple[str, ...]]:
    """Every navigation of a typed tree as (class, feature, feature…), in order of appearance."""
    out: list[tuple[str, ...]] = []
    k = node["k"]
    if k == "path" and node.get("ref") and len(node["ref"]) > 1 and not node["ref"][0].startswith("@"):
        out.append(tuple(node["ref"]))
    for key in ("x", "l", "r"):
        if key in node and isinstance(node[key], dict):
            out += features_used(node[key])
    for x in node.get("items", []):
        out += features_used(x)
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
        return f"{to_text(node['l'])} {node['op']} {to_text(node['r'])}"
    if k == "in":
        return f"{to_text(node['x'])} in [{', '.join(to_text(i) for i in node['items'])}]"
    return "?"


def _wrap(node: dict[str, Any], outer: str) -> str:
    s = to_text(node)
    inner = node["k"]
    if inner in ("and", "or") and (inner != outer or outer == "not"):
        return f"({s})"
    if outer == "not" and inner in ("cmp", "in"):
        return f"({s})"
    return s
