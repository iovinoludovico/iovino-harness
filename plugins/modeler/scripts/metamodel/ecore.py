"""The domain metamodel in Ecore notation (`domain.ecore.yaml`).

The metamodel says *what* the domain of an application is: package, classes (abstract, supertypes),
attributes, references (containment, multiplicity, opposite), enums. It is written from the prompt, edited
in the web modeler that lives inside the application (admin area), or derived from an existing database
(`reverse`), and checked against the live database (`drift`).

`storage()` gives the deterministic database mapping (tables, columns, foreign keys, join tables) used by
drift and shown to the developer; the application code itself is written by hand and kept aligned.
"""

from __future__ import annotations

import copy
import difflib
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from . import core as M

METAMODEL_FILE = "domain.ecore.yaml"
BEHAVIOR_FILE = "behavior.yaml"     # the behaviour model (behavior.py), next to the metamodel
CLASS_NAME = re.compile(r"^[A-Z][A-Za-z0-9]{1,39}$")
FEATURE_NAME = re.compile(r"^[a-z][A-Za-z0-9_]{0,39}$")
LITERAL_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,39}$")
BUILTIN_CLASSES = {"User"}          # application users (table `profiles`): referenced, never declared

# Ecore data types and the storage type they map to.
DATATYPES: dict[str, str] = {
    "EString": "string", "EInt": "int", "ELong": "int", "EShort": "int", "EBigInteger": "int",
    "EDouble": "number", "EFloat": "number", "EBigDecimal": "number", "EBoolean": "bool",
    "EDate": "datetime", "Text": "text", "Email": "email", "URL": "url", "Money": "money",
    "Date": "date", "DateTime": "datetime", "JSON": "json",
}
# storage type -> preferred data type (used by reverse)
TYPE_TO_DATATYPE = {
    "string": "EString", "text": "Text", "email": "Email", "url": "URL", "int": "EInt", "number": "EDouble",
    "money": "Money", "bool": "EBoolean", "date": "Date", "datetime": "EDate", "json": "JSON",
}
# custom data types declared in the exported .ecore (instance classes for Java tools)
CUSTOM_DATATYPES = {"Text": "java.lang.String", "Email": "java.lang.String", "URL": "java.lang.String",
                    "Money": "java.math.BigDecimal", "Date": "java.time.LocalDate",
                    "DateTime": "java.util.Date", "JSON": "java.lang.String"}

CLASS_KEYS = {"abstract", "supertypes", "doc", "label", "plural", "table", "unique", "attributes", "references", "rules"}
ATTRIBUTE_KEYS = {"type", "lower", "upper", "default", "id", "unique", "changeable", "derived", "doc", "label", "help",
                  "list", "min", "max", "max_length", "renamed_from", "column"}
REFERENCE_KEYS = {"type", "lower", "upper", "containment", "opposite", "doc", "label", "help", "list",
                  "on_delete", "unique", "renamed_from", "column", "join_table"}
# columns every table may have that the metamodel does not describe (managed by the database)
STANDARD_COLUMNS = {"id", "created_at", "updated_at"}
TOP_KEYS = {"package", "nsURI", "nsPrefix", "doc", "language", "classes", "enums", "rules", "diagram"}
LANGUAGES = {"en", "it"}
# domain rules the structure cannot express: [{id, text}] on the package or on a class; shown in docs/DOMAIN.md
RULE_ID = re.compile(r"^[a-z][a-z0-9_]*$")
RULE_KEYS = {"id", "text"}


class MetamodelError(Exception):
    pass


# --------------------------------------------------------------------------- #
# Loading and canonical form
# --------------------------------------------------------------------------- #
def load(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise M.ModelError(f"metamodel file not found: {path}")
    raw = M.loads(path.read_text(encoding="utf-8")) if path.suffix != ".ecore" else import_ecore(path.read_text(encoding="utf-8"))
    return raw


def loads(text: str) -> dict[str, Any]:
    return M.loads(text)


def metamodel_path(app_file: str | Path) -> Path:
    return Path(app_file).resolve().parent / METAMODEL_FILE


def _upper(value: Any) -> int:
    if value in (None, ""):
        return 1
    if value in ("*", "-1", -1, "many"):
        return -1
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 1
    return -1 if n > 1 or n < 0 else n


def expand(raw: dict[str, Any]) -> dict[str, Any]:
    """Canonical form: every feature a full mapping, every enum {literals: [{name, label?}]}.
    Never raises; malformed parts are kept as they are for validate()."""
    out: dict[str, Any] = {
        "package": raw.get("package") or "domain",
        "nsURI": raw.get("nsURI") or "",
        "nsPrefix": raw.get("nsPrefix") or "",
        "doc": raw.get("doc") or "",
        "language": raw.get("language") or "en",
        "classes": {},
        "enums": {},
        "rules": copy.deepcopy(raw.get("rules") or []),
        "diagram": copy.deepcopy(raw.get("diagram") or {}),
    }
    for cname, cspec in (raw.get("classes") or {}).items():
        cspec = cspec if isinstance(cspec, dict) else {}
        cls: dict[str, Any] = {k: copy.deepcopy(v) for k, v in cspec.items() if k not in ("attributes", "references")}
        cls["abstract"] = bool(cspec.get("abstract", False))
        if "rules" in cls and cls["rules"] is None:
            cls["rules"] = []
        sup = cspec.get("supertypes") or []
        cls["supertypes"] = [str(s) for s in (sup if isinstance(sup, list) else [sup])]
        if "unique" in cspec:   # combinations that must be unique: one group [a, b] or several [[a, b], [c, d]]
            groups = cspec["unique"] if isinstance(cspec["unique"], list) else [cspec["unique"]]
            if groups and all(isinstance(g, str) for g in groups):
                groups = [groups]
            cls["unique"] = [[str(f) for f in g] if isinstance(g, list) else g for g in groups]
        cls["attributes"] = {}
        for an, aspec in (cspec.get("attributes") or {}).items():
            aspec = {"type": aspec} if isinstance(aspec, str) else dict(aspec or {})
            aspec.setdefault("type", "EString")
            aspec["lower"] = int(aspec.get("lower", 0) or 0)
            aspec["upper"] = _upper(aspec.get("upper"))
            cls["attributes"][str(an)] = aspec
        cls["references"] = {}
        for rn, rspec in (cspec.get("references") or {}).items():
            rspec = {"type": rspec} if isinstance(rspec, str) else dict(rspec or {})
            rspec["lower"] = int(rspec.get("lower", 0) or 0)
            rspec["upper"] = _upper(rspec.get("upper"))
            rspec["containment"] = bool(rspec.get("containment", False))
            cls["references"][str(rn)] = rspec
        out["classes"][str(cname)] = cls
    for ename, espec in (raw.get("enums") or {}).items():
        if isinstance(espec, list):
            espec = {"literals": espec}
        espec = dict(espec or {})
        lits = []
        for lit in espec.get("literals") or espec.get("values") or []:
            if isinstance(lit, dict):
                if "name" in lit or "key" in lit:
                    d = {"name": str(lit.get("name", lit.get("key")))}
                    if lit.get("label") is not None:
                        d["label"] = lit["label"]
                    lits.append(d)
                elif len(lit) == 1:
                    k, lab = next(iter(lit.items()))
                    lits.append({"name": str(k), "label": lab})
            else:
                lits.append({"name": str(lit)})
        e = {k: v for k, v in espec.items() if k not in ("literals", "values")}
        e["literals"] = lits
        out["enums"][str(ename)] = e
    return out


def compact(raw: dict[str, Any]) -> dict[str, Any]:
    """The most readable YAML form of a metamodel (shorthands, defaults omitted)."""
    e = expand(raw)
    out: dict[str, Any] = {"package": e["package"]}
    for k in ("nsURI", "nsPrefix", "doc"):
        if e[k]:
            out[k] = e[k]
    if e["language"] != "en":
        out["language"] = e["language"]
    classes: dict[str, Any] = {}
    for cname, c in e["classes"].items():
        cls: dict[str, Any] = {}
        for k in ("abstract", "supertypes", "doc", "label", "plural", "table", "unique"):
            v = c.get(k)
            if v not in (None, False, [], ""):
                cls[k] = v
        attrs = {}
        for an, a in c["attributes"].items():
            a = {k: v for k, v in a.items() if not (k == "lower" and v == 0) and not (k == "upper" and v == 1)}
            attrs[an] = a["type"] if list(a) == ["type"] else a
        refs = {}
        for rn, r in c["references"].items():
            r = {k: v for k, v in r.items() if not (k == "lower" and v == 0) and not (k == "upper" and v == 1)
                 and not (k == "containment" and v is False)}
            refs[rn] = r["type"] if list(r) == ["type"] else r
        if attrs:
            cls["attributes"] = attrs
        if refs:
            cls["references"] = refs
        if c.get("rules"):
            cls["rules"] = c["rules"]
        classes[cname] = cls
    out["classes"] = classes
    enums = {}
    for en, en_spec in e["enums"].items():
        lits = en_spec["literals"]
        rest = {k: v for k, v in en_spec.items() if k != "literals"}
        if all(list(lit) == ["name"] for lit in lits) and not rest:
            enums[en] = [lit["name"] for lit in lits]
        else:
            enums[en] = {**rest, "literals": [lit["name"] if list(lit) == ["name"] else lit for lit in lits]}
    if enums:
        out["enums"] = enums
    if e["rules"]:
        out["rules"] = e["rules"]
    if e["diagram"]:
        out["diagram"] = e["diagram"]
    return out


def _flow_dumper():
    yaml = M.import_yaml()

    class Dumper(yaml.SafeDumper):
        pass

    def is_scalar(v: Any) -> bool:
        return isinstance(v, (str, int, float, bool)) or v is None

    def is_leaf(v: Any) -> bool:
        return is_scalar(v) or (isinstance(v, list) and all(is_scalar(x) for x in v)) or (
            isinstance(v, dict) and all(is_scalar(x) for x in v.values()) and len(str(v)) < 60)

    def rep_dict(dumper, data):
        flow = bool(data) and len(data) <= 8 and all(is_leaf(v) for v in data.values()) and len(str(data)) < 130
        return dumper.represent_mapping("tag:yaml.org,2002:map", data.items(), flow_style=flow)

    def rep_list(dumper, data):
        flow = all(isinstance(x, (str, int, float, bool)) for x in data) and len(str(data)) < 100
        return dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=flow)

    Dumper.add_representer(dict, rep_dict)
    Dumper.add_representer(list, rep_list)
    Dumper.add_representer(_Block, lambda d, data: d.represent_mapping("tag:yaml.org,2002:map", data.items(), flow_style=False))
    return yaml, Dumper


class _Block(dict):
    """A mapping always written in block style."""


def dumps(raw: dict[str, Any]) -> str:
    header = ("# Domain metamodel (Ecore notation): the source of truth of the domain. Edit it from the prompt\n"
              "# (/modeler:metamodel), in the app's modeler (/admin/model) or by hand, together with a migration.\n")
    yaml, Dumper = _flow_dumper()
    body = compact(raw)
    text = ""
    for key, value in body.items():   # blank line between sections, classes separated too
        if key in ("classes", "enums", "diagram") and isinstance(value, dict):
            text += f"\n{key}:\n"
            for cname, c in value.items():
                chunk = yaml.dump(_Block({cname: c}), Dumper=Dumper, sort_keys=False, allow_unicode=True, width=120)
                text += "".join("  " + line + "\n" for line in chunk.rstrip("\n").split("\n"))
        elif isinstance(value, (str, int, float, bool)):
            scalar = yaml.safe_dump(value, allow_unicode=True, width=1000).strip()
            text += f"{key}: {scalar.removesuffix('...').strip()}\n"
        else:
            body_text = yaml.dump(value, Dumper=Dumper, sort_keys=False, allow_unicode=True, width=120)
            text += ("\n" if key in ("enums", "rules", "diagram") else "") + f"{key}:\n" + "".join(
                "  " + line + "\n" for line in body_text.rstrip("\n").split("\n"))
    return header + text


def align_order(new: Any, old: Any) -> Any:
    """`new` with the keys in the order of `old` (classes, features, keys of a feature, enums, diagram), the keys
    that `old` lacks after them. A proposal comes back from the editor or from a jsonb column with its keys
    reordered: aligned, rewriting the metamodel changes only the lines of what really changed. Lists (literals,
    supertypes, unique groups) keep their own order."""
    if not isinstance(new, dict) or not isinstance(old, dict):
        return new
    keys = [k for k in old if k in new] + [k for k in new if k not in old]
    return {k: align_order(new[k], old.get(k)) for k in keys}


def comment_lines(text: str) -> list[str]:
    """Comments written by hand in a metamodel file (the header written by dumps excluded): rewriting loses them.
    Inline comments are recognised by ` # ` (a value containing it is reported too: a harmless false alarm)."""
    header = set(dumps({"package": "x", "classes": {}}).splitlines()[:2])
    return [line for line in text.splitlines()
            if line not in header and (line.lstrip().startswith("#") or " # " in line)]


# --------------------------------------------------------------------------- #
# Surgical rewrite: only the lines of what changed
# --------------------------------------------------------------------------- #
def _yaml_lines(value: dict[str, Any], indent: int) -> list[str]:
    """`value` ({name: spec}) as dumps writes it (one block entry per name), indented by `indent` spaces."""
    yaml, Dumper = _flow_dumper()
    chunk = yaml.dump(_Block(value), Dumper=Dumper, sort_keys=False, allow_unicode=True, width=120)
    return [" " * indent + line for line in chunk.rstrip("\n").split("\n")]


def _yaml_list_lines(value: list[Any], indent: int) -> list[str]:
    """A list as dumps writes it (`- {id: x, text: …}` items), indented by `indent` spaces."""
    yaml, Dumper = _flow_dumper()
    chunk = yaml.dump(value, Dumper=Dumper, sort_keys=False, allow_unicode=True, width=120)
    return [" " * indent + line for line in chunk.rstrip("\n").split("\n")]


def _children(lines: list[str], start: int, end: int, indent: int) -> dict[str, tuple[int, int]]:
    """The keys written at exactly `indent` spaces in lines[start:end]: {key: (first line, end line)}.
    Blank and comment lines stay with the key above them."""
    out: dict[str, tuple[int, int]] = {}
    key_re = re.compile(rf"^ {{{indent}}}([A-Za-z_][\w]*)\s*:")
    current = None
    for i in range(start, end):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        depth = len(line) - len(line.lstrip())
        m = key_re.match(line)
        if m and depth == indent:
            if current:
                out[current] = (out[current][0], i)
            current = m.group(1)
            out[current] = (i, end)
        elif depth < indent:
            break
    if current:
        out[current] = (out[current][0], max(i for i in range(out[current][0], end)
                                              if lines[i].strip() and not lines[i].lstrip().startswith("#")) + 1)
    return out


def _inline(line: str) -> bool:
    """A key written with its value on the same line (`attributes: {a: X}`), a trailing comment aside."""
    return bool(line.split(":", 1)[1].split(" #", 1)[0].strip())


def patch_text(text: str, new: dict[str, Any]) -> str | None:
    """`text` (the current metamodel file) changed into `new` rewriting only what differs: one feature line, else
    the block of one class or enum, else the diagram. None when the file is not in the expected layout or the
    change touches the package header: the caller then rewrites the whole file."""
    try:
        old = loads(text)
    except Exception:  # noqa: BLE001 - an unreadable file is rewritten
        return None
    a, b = expand(old), expand(new)
    if any(a[k] != b[k] for k in ("package", "nsURI", "nsPrefix", "doc", "language")):
        return None
    cb = compact(new)
    lines = text.split("\n")
    top = _children(lines, 0, len(lines), 0)
    edits: list[tuple[int, int, list[str]]] = []   # (start, end, replacement)

    def feature_edits(cname: str, cs: int, ce: int) -> list[tuple[int, int, list[str]]] | None:
        ca, cn = a["classes"][cname], b["classes"][cname]
        if {k: v for k, v in ca.items() if k not in ("attributes", "references")} != \
                {k: v for k, v in cn.items() if k not in ("attributes", "references")}:
            return None
        found: list[tuple[int, int, list[str]]] = []
        keys = _children(lines, cs + 1, ce, 4)
        for kind in ("attributes", "references"):
            if ca[kind] == cn[kind]:
                continue
            if kind not in keys or _inline(lines[keys[kind][0]]):
                return None                           # missing or written inline: rewrite the class
            ks, ke = keys[kind]
            feats = _children(lines, ks + 1, ke, 6)
            if set(feats) != set(ca[kind]):
                return None
            new_feats = cb["classes"][cname].get(kind, {})
            for fname in ca[kind]:
                if fname not in cn[kind]:
                    found.append((*feats[fname], []))
                elif ca[kind][fname] != cn[kind][fname]:
                    found.append((*feats[fname], _yaml_lines({fname: new_feats[fname]}, 6)))
            added = [f for f in cn[kind] if f not in ca[kind]]
            if added:
                last = max(e for _, e in feats.values()) if feats else ks + 1
                found.append((last, last, [x for f in added for x in _yaml_lines({f: new_feats[f]}, 6)]))
        return found

    for section in ("classes", "enums"):
        if a[section] == b[section]:
            continue
        if section not in top or _inline(lines[top[section][0]]):
            return None
        ss, se = top[section]
        blocks = _children(lines, ss + 1, se, 2)
        if set(blocks) != set(a[section]):
            return None
        for name in a[section]:
            if name not in b[section]:
                edits.append((*blocks[name], []))
            elif a[section][name] != b[section][name]:
                fe = feature_edits(name, *blocks[name]) if section == "classes" else None
                edits += fe if fe is not None else [(*blocks[name], _yaml_lines({name: cb[section][name]}, 2))]
        added = [n for n in b[section] if n not in a[section]]
        if added:
            last = max(e for _, e in blocks.values()) if blocks else ss + 1
            edits.append((last, last, [x for n in added for x in _yaml_lines({n: cb[section][n]}, 2)]))
    if a["diagram"] != b["diagram"]:
        if "diagram" not in top or not b["diagram"]:
            return None
        ds, de = top["diagram"]
        edits.append((ds, de, ["diagram:"] + _yaml_lines(cb["diagram"], 2)))
    if a["rules"] != b["rules"]:                     # package rules: their own top-level block
        block = ["rules:"] + _yaml_list_lines(cb["rules"], 2) if b["rules"] else []
        if "rules" in top:
            edits.append((*top["rules"], block))
        elif block:                                  # new block before the diagram, else after the last key
            if "diagram" in top:
                edits.append((top["diagram"][0], top["diagram"][0], block + [""]))
            else:
                at = max(e for _, e in top.values())
                edits.append((at, at, [""] + block))
    for start, end, repl in sorted(edits, key=lambda x: (x[0], x[1]), reverse=True):
        lines[start:end] = repl
    out = "\n".join(lines)
    try:
        if expand(loads(out)) != b:          # never write a file that does not read back as the proposal
            return None
    except Exception:  # noqa: BLE001
        return None
    return out


def dump(raw: dict[str, Any], path: str | Path) -> None:
    Path(path).write_text(dumps(raw), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def _all_supertypes(e: dict[str, Any], cname: str, rep: M.Report | None = None) -> list[str]:
    """Ancestors of a class, farthest first, without duplicates. Reports cycles."""
    seen: list[str] = []

    def visit(n: str, path: list[str]) -> None:
        for s in e["classes"].get(n, {}).get("supertypes", []):
            if s in path:
                if rep is not None:
                    rep.error(f"classes.{cname}", f"inheritance cycle: {' -> '.join(path + [s])}")
                continue
            if s not in e["classes"]:
                continue
            visit(s, path + [s])
            if s not in seen:
                seen.append(s)

    visit(cname, [cname])
    return seen


def features(e: dict[str, Any], cname: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Attributes and references of a class, inherited ones first."""
    attrs: dict[str, Any] = {}
    refs: dict[str, Any] = {}
    for c in _all_supertypes(e, cname) + [cname]:
        cls = e["classes"].get(c) or {}
        for k, v in cls.get("attributes", {}).items():
            attrs[k] = {**v, "_owner": c}
        for k, v in cls.get("references", {}).items():
            refs[k] = {**v, "_owner": c}
    return attrs, refs


def concrete_descendants(e: dict[str, Any], cname: str) -> list[str]:
    return [n for n, c in e["classes"].items() if not c["abstract"] and (n == cname or cname in _all_supertypes(e, n))]


def resolve_type(e: dict[str, Any], tname: str) -> str | None:
    """The concrete class a reference points to (an abstract type with a single concrete subclass is fine)."""
    if tname in BUILTIN_CLASSES:
        return tname
    if tname not in e["classes"]:
        return None
    conc = concrete_descendants(e, tname)
    return conc[0] if len(conc) == 1 else None


def validate(raw: dict[str, Any]) -> M.Report:
    rep = M.Report()
    unknown = set(raw) - TOP_KEYS
    if unknown:
        rep.error("metamodel", f"unknown top-level keys: {', '.join(sorted(map(str, unknown)))} "
                  "(the metamodel describes structure only: workflows, derivations, events and reactions live in "
                  f"{BEHAVIOR_FILE})")
    e = expand(raw)
    _check_rules(e["rules"], "rules", rep)
    if e["language"] not in LANGUAGES:
        rep.error("language", f"must be one of {', '.join(sorted(LANGUAGES))} (names of tables and plurals)")
    if not re.match(r"^[a-z][A-Za-z0-9_]*$", e["package"]):
        rep.error("package", f"'{e['package']}' is not a valid package name (lowercase identifier)")
    if not e["classes"]:
        rep.error("classes", "the metamodel declares no classes")
    for en, espec in e["enums"].items():
        where = f"enums.{en}"
        if not CLASS_NAME.match(en):
            rep.error(where, "enum names are PascalCase")
        if en in e["classes"]:
            rep.error(where, "an enum and a class have the same name")
        names = [lit["name"] for lit in espec["literals"]]
        if not names:
            rep.error(where, "no literals")
        for n in names:
            if not LITERAL_NAME.match(n):
                rep.error(where, f"invalid literal '{n}'")
        if len(set(names)) != len(names):
            rep.error(where, "duplicate literals")
    for cname, c in e["classes"].items():
        where = f"classes.{cname}"
        if cname in BUILTIN_CLASSES:
            rep.error(where, f"{cname} is built in (the application users): reference it, do not declare it")
            continue
        if not CLASS_NAME.match(cname):
            rep.error(where, "class names are PascalCase (letters and digits, 2-40 characters)")
        extra = set(c) - CLASS_KEYS
        if extra:
            rep.error(where, f"unknown keys: {', '.join(sorted(extra))} (allowed: {', '.join(sorted(CLASS_KEYS))})")
        if "rules" in c:
            _check_rules(c["rules"], f"{where}.rules", rep)
        for s in c["supertypes"]:
            if s not in e["classes"]:
                rep.error(where, f"unknown supertype '{s}'")
        _all_supertypes(e, cname, rep)
        _check_unique_groups(e, cname, c, where, rep)
        own = list(c["attributes"]) + list(c["references"])
        dup = {n for n in own if own.count(n) > 1}
        if dup:
            rep.error(where, f"features declared twice: {', '.join(sorted(dup))}")
        for an, a in c["attributes"].items():
            fw = f"{where}.attributes.{an}"
            _check_feature_name(an, fw, rep)
            bad = set(a) - ATTRIBUTE_KEYS
            if bad:
                rep.error(fw, f"unknown keys: {', '.join(sorted(bad))}")
            t = str(a.get("type"))
            if t not in DATATYPES and t not in e["enums"]:
                hint = " (a class: declare it under references)" if t in e["classes"] or t in BUILTIN_CLASSES else ""
                rep.error(fw, f"unknown data type '{t}'{hint}; use {', '.join(DATATYPES)} or an enum")
            if a["upper"] != 1:
                rep.warn(fw, "multi-valued attribute: stored as a JSON array")
            if a.get("default") is not None and t in e["enums"]:
                if str(a["default"]) not in [lit["name"] for lit in e["enums"][t]["literals"]]:
                    rep.error(fw, f"default '{a['default']}' is not a literal of {t}")
            if a.get("derived"):
                if a.get("id"):
                    rep.error(fw, "a derived attribute cannot be the id")
                if a.get("changeable") is True:
                    rep.error(fw, "a derived attribute is read only: drop changeable: true")
        for rn, r in c["references"].items():
            fw = f"{where}.references.{rn}"
            _check_feature_name(rn, fw, rep)
            bad = set(r) - REFERENCE_KEYS
            if bad:
                rep.error(fw, f"unknown keys: {', '.join(sorted(bad))}")
            t = str(r.get("type"))
            if t not in e["classes"] and t not in BUILTIN_CLASSES:
                hint = " (a data type or enum: declare it under attributes)" if t in DATATYPES or t in e["enums"] else ""
                rep.error(fw, f"unknown class '{t}'{hint}")
                continue
            if t not in BUILTIN_CLASSES and resolve_type(e, t) is None:
                conc = concrete_descendants(e, t)
                rep.error(fw, f"references abstract class {t} with {len(conc)} concrete subclasses "
                              f"({', '.join(conc) or 'none'}): polymorphic references are not supported; "
                              "reference a concrete class")
            if r["containment"] and t in BUILTIN_CLASSES:
                rep.error(fw, f"{t} cannot be contained")
            raw_r = ((raw.get("classes") or {}).get(cname) or {}).get("references", {}).get(rn)
            raw_up = raw_r.get("upper") if isinstance(raw_r, dict) else None
            if isinstance(raw_up, int) and raw_up > 1 or (isinstance(raw_up, str) and raw_up.isdigit() and int(raw_up) > 1):
                rep.warn(fw, f"finite maximum (upper: {raw_up}) is stored as many: the model does not enforce it "
                             "(a trigger of the application on the table of the parts)")
            if r.get("on_delete") and r["on_delete"] not in ("restrict", "set_null", "cascade"):
                rep.error(fw, "on_delete must be restrict, set_null or cascade")
            opp = r.get("opposite")
            if opp:
                if t in BUILTIN_CLASSES:
                    rep.error(fw, f"{t} is built in: it cannot declare the opposite '{opp}'")
                    continue
                _, trefs = features(e, t)
                o = trefs.get(opp)
                if not o:
                    rep.error(fw, f"opposite '{opp}' is not a reference of {t}")
                    continue
                back = o.get("type")
                if back != cname and back not in _all_supertypes(e, cname):
                    rep.error(fw, f"opposite {t}.{opp} points to {back}, not to {cname}")
                if o.get("opposite") != rn:
                    rep.error(fw, f"opposite {t}.{opp} must declare opposite: {rn}")
                if r["containment"] and o["containment"]:
                    rep.error(fw, "both ends of a reference pair cannot be containments")
    # features inherited twice under the same name
    for cname, c in e["classes"].items():
        if c["abstract"] or cname in BUILTIN_CLASSES:
            continue
        seen: dict[str, str] = {}
        for anc in _all_supertypes(e, cname) + [cname]:
            cls = e["classes"].get(anc, {})
            for n in list(cls.get("attributes", {})) + list(cls.get("references", {})):
                if n in seen and seen[n] != anc:
                    rep.error(f"classes.{cname}", f"feature '{n}' declared in both {seen[n]} and {anc}")
                seen[n] = anc
    if not any(not c["abstract"] for c in e["classes"].values()) and e["classes"]:
        rep.error("classes", "every class is abstract: nothing to store")
    if rep.ok:
        storage(raw, rep)   # columns that clash once references are placed
    return rep


def _check_rules(rules: Any, where: str, rep: M.Report) -> None:
    """`rules`: a list of {id, text}; ids are lowercase identifiers, unique in their scope."""
    if not isinstance(rules, list):
        rep.error(where, "a list of {id, text} mappings")
        return
    seen: set[str] = set()
    for i, r in enumerate(rules):
        w = f"{where}[{i}]"
        if not isinstance(r, dict):
            rep.error(w, "a rule is a mapping {id, text} (a comma or colon in the text: quote it)")
            continue
        rid = r.get("id")
        if not isinstance(rid, str) or not RULE_ID.match(rid):
            rep.error(w, f"id {rid!r}: lowercase identifier (letters, digits, _)")
        elif rid in seen:
            rep.error(w, f"rule id '{rid}' declared twice")
        else:
            seen.add(rid)
        if not isinstance(r.get("text"), str) or not r["text"].strip():
            rep.error(w, "text: the rule in one sentence")
        extra = set(r) - RULE_KEYS
        if extra:
            rep.error(w, f"unknown keys: {', '.join(sorted(map(str, extra)))} (allowed: id, text)")


def _check_unique_groups(e: dict[str, Any], cname: str, c: dict[str, Any], where: str, rep: M.Report) -> None:
    """Class-level `unique`: groups of two or more single-valued features (own or inherited)."""
    if "unique" not in c:
        return
    attrs, refs = features(e, cname)
    for g in c["unique"]:
        if not isinstance(g, list) or len(g) < 2:
            rep.error(f"{where}.unique", f"{g!r}: a group lists two or more features (one feature: unique: true on it)")
            continue
        if len(set(g)) != len(g):
            rep.error(f"{where}.unique", f"{g}: a feature is listed twice")
        for f in g:
            spec = attrs.get(f) or refs.get(f)
            if spec is None:
                rep.error(f"{where}.unique", f"'{f}' is not a feature of {cname}")
            elif spec["upper"] != 1:
                rep.error(f"{where}.unique", f"'{f}' is multi-valued: only single-valued features can be unique together")


def _check_feature_name(name: str, where: str, rep: M.Report) -> None:
    if not FEATURE_NAME.match(name):
        rep.error(where, "feature names start lowercase (camelCase or snake_case)")
        return
    col = M.snake(name)
    if col in STANDARD_COLUMNS:
        rep.error(where, f"'{name}' is a standard column ({col}): rename it")


# --------------------------------------------------------------------------- #
# Storage: how the metamodel maps to tables and columns
# --------------------------------------------------------------------------- #
def plural_word(word: str, language: str) -> str:
    if language != "it":
        return M.pluralize(word)
    w = word
    low = w.lower()
    if not low or low[-1] not in "aeio" or low[-1] in "àèéìòù" or len(low) <= 2:
        return w                                   # loanwords, truncated and accented words do not change
    if low.endswith(("ca", "ga")):
        return w[:-1] + "he"
    if low.endswith(("co", "go")) and len(low) > 4 and low[-3] in "aeiou":
        return w[:-1] + "i" if low[-2] == "c" else w[:-1] + "hi"
    if low.endswith(("co", "go")):
        return w[:-1] + "hi"
    if low.endswith("io"):
        return w[:-1]
    if low.endswith(("cia", "gia")) and low[-4:-3] not in "aeiou":
        return w[:-2] + "e"
    if low.endswith("a"):
        return w[:-1] + "e"
    return w[:-1] + "i"


def default_table(cname: str, language: str) -> str:
    words = M.snake(cname).split("_")
    if language == "it":
        words[0] = plural_word(words[0], "it")
    else:
        words[-1] = M.pluralize(words[-1])
    return "_".join(words)


def field_key(feature: str, spec: dict[str, Any] | None = None) -> str:
    """Stored column of a feature: `column` if given (adopted databases), else snake_case of the name."""
    if spec and spec.get("column"):
        return str(spec["column"])
    return M.snake(feature)


def literal_key(name: str) -> str:
    """Enum literal -> stored value: ADMIN, inProgress, IN_PROGRESS -> admin, in_progress, in_progress."""
    return M.snake(name).lower()


def reference_columns(e: dict[str, Any]) -> list[dict[str, Any]]:
    """Where each reference is stored. One entry per stored column / join table:
    {holder, field, target, many, required, on_delete, unique, from: (class, ref), inverse: (class, ref)|None}."""
    out: list[dict[str, Any]] = []
    done: set[tuple[str, str]] = set()
    order = {n: i for i, n in enumerate(e["classes"])}
    containers: dict[str, int] = {}
    for cname, c in e["classes"].items():
        if c["abstract"]:
            continue
        _, refs = features(e, cname)
        for rn, r in refs.items():
            if r["containment"]:
                t = resolve_type(e, str(r["type"]))
                if t:
                    containers[t] = containers.get(t, 0) + 1
    for cname, c in e["classes"].items():
        if c["abstract"]:
            continue
        _, refs = features(e, cname)
        for rn, r in refs.items():
            if (cname, rn) in done:
                continue
            t = resolve_type(e, str(r["type"]))
            if not t:
                continue
            opp = r.get("opposite")
            o = None
            if opp and t not in BUILTIN_CLASSES:
                _, trefs = features(e, t)
                o = trefs.get(opp)
            done.add((cname, rn))
            if o is not None:
                done.add((t, opp))
            r_many, o_many = r["upper"] != 1, (o is not None and o["upper"] != 1)
            if o is None:
                if r["containment"]:     # the contained class gets a required link to its container
                    out.append({"holder": t, "field": field_key(cname) if not r_many else field_key(cname),
                                "target": cname, "many": False, "required": containers.get(t, 0) <= 1,
                                "on_delete": "cascade", "unique": not r_many, "from": (cname, rn), "inverse": None,
                                "spec": {}})
                elif r_many:
                    out.append({"holder": cname, "field": field_key(rn, r), "target": t, "many": True, "required": False,
                                "on_delete": None, "unique": False, "from": (cname, rn), "inverse": None, "spec": r})
                else:
                    out.append({"holder": cname, "field": field_key(rn, r), "target": t, "many": False,
                                "required": r["lower"] >= 1, "on_delete": r.get("on_delete"),
                                "unique": bool(r.get("unique")), "from": (cname, rn), "inverse": None, "spec": r})
                continue
            # a pair of opposite references
            if r_many and o_many:
                first = (cname, rn) if order[cname] <= order.get(t, 0) else (t, opp)
                holder, fname, spec = (first[0], first[1], r if first == (cname, rn) else o)
                target = t if holder == cname else cname
                out.append({"holder": holder, "field": field_key(fname, spec), "target": target, "many": True,
                            "required": False, "on_delete": None, "unique": False, "from": first,
                            "inverse": (cname, rn) if first != (cname, rn) else (t, opp), "spec": spec})
                continue
            if r_many and not o_many:
                side, other = (t, opp, o, cname), (cname, rn, r)
            elif o_many and not r_many:
                side, other = (cname, rn, r, t), (t, opp, o)
            else:   # one-to-one: the contained side, else the mandatory side, else the first declared
                if r["containment"]:
                    pick_o = True
                elif o["containment"]:
                    pick_o = False
                elif o["lower"] >= 1 and r["lower"] == 0:
                    pick_o = True
                else:
                    pick_o = False
                side, other = ((t, opp, o, cname), (cname, rn, r)) if pick_o else ((cname, rn, r, t), (t, opp, o))
            holder, fname, spec, target = side
            contained = other[2]["containment"]
            out.append({"holder": holder, "field": field_key(fname, spec), "target": target, "many": False,
                        "required": spec["lower"] >= 1 or contained,
                        "on_delete": "cascade" if contained else spec.get("on_delete"),
                        "unique": not (r_many or o_many) or bool(spec.get("unique")),
                        "from": (holder, fname), "inverse": (other[0], other[1]), "spec": spec})
    return out


def _attribute_field(e: dict[str, Any], key: str, name: str, a: dict[str, Any]) -> dict[str, Any]:
    t = str(a["type"])
    f: dict[str, Any] = {"key": key, "type": DATATYPES.get(t, "string"), "enum": None, "to": None, "many": False,
                         "required": a["lower"] >= 1, "unique": bool(a.get("id") or a.get("unique")),
                         "on_delete": None, "default": a.get("default"), "max_length": a.get("max_length"),
                         "feature": name, "renamed_from": a.get("renamed_from")}
    if a["upper"] != 1:
        f["type"] = "json"
    elif t in e["enums"]:
        f["type"], f["enum"] = "enum", t
        if a.get("default") is not None:
            f["default"] = literal_key(str(a["default"]))
    return f


def storage(meta: dict[str, Any], rep: M.Report | None = None) -> dict[str, Any]:
    """Tables and columns described by the metamodel:
    {"enums": {name: [stored values]}, "entities": {class: {"table", "display", "fields": {column: {...}}}}}.
    Abstract classes have no table (their features are flattened into the concrete subclasses);
    many-valued references (`many: True`) are join tables `<table>_<column>` unless `join_table` is given.
    `feature` is the feature stored in the column (None for the link of a contained class to its container);
    `unique` lists the column groups that are unique together (class-level `unique`, nulls not distinct)."""
    rep = rep if rep is not None else M.Report()
    e = expand(meta)
    enums = {en: [literal_key(lit["name"]) for lit in spec["literals"]] for en, spec in e["enums"].items()}
    columns = reference_columns(e)
    entities: dict[str, Any] = {}
    for cname, c in e["classes"].items():
        if c["abstract"] or cname in BUILTIN_CLASSES:
            continue
        fields: dict[str, Any] = {}
        attrs, _ = features(e, cname)
        for an, a in attrs.items():
            key = field_key(an, a)
            fields[key] = _attribute_field(e, key, an, a)
        for col in columns:
            if col["holder"] != cname:
                continue
            key = col["field"]
            if key in fields:
                rep.error(f"classes.{cname}", f"'{key}' is both an attribute and a reference column")
                continue
            fields[key] = {"key": key, "type": "ref", "enum": None, "to": col["target"], "many": col["many"],
                           "required": col["required"], "unique": bool(col["unique"] and not col["many"]),
                           "on_delete": col["on_delete"] or (None if col["many"] else ("restrict" if col["required"] else "set_null")),
                           "default": None, "join_table": col["spec"].get("join_table") if col["many"] else None,
                           "max_length": None,
                           "feature": col["from"][1] if col["from"][0] == cname else None,
                           "renamed_from": col["spec"].get("renamed_from") if col["from"][0] == cname else None}
        column_of = {f["feature"]: k for k, f in fields.items() if f.get("feature") and not f["many"]}
        uniques: list[list[str]] = []
        for anc in _all_supertypes(e, cname) + [cname]:
            for g in e["classes"].get(anc, {}).get("unique") or []:
                if not isinstance(g, list) or len(g) < 2:
                    continue
                missing = [f for f in g if f not in column_of]
                if missing:
                    rep.error(f"classes.{anc}.unique", f"{', '.join(missing)}: not a column of {cname} "
                              "(a reference counts only when its foreign key is in this table)")
                    continue
                uniques.append([column_of[f] for f in g])
        entities[cname] = {
            "table": c.get("table") or default_table(cname, e["language"]),
            "display": next((field_key(n, a) for n, a in attrs.items() if a.get("id")), None),
            "fields": fields,
            "unique": uniques,
        }
    return {"enums": enums, "entities": entities}

# --------------------------------------------------------------------------- #
# Views: Emfatic-like text, Mermaid, runtime JSON, diff
# --------------------------------------------------------------------------- #
def _mult(lower: int, upper: int) -> str:
    if lower == 0 and upper == 1:
        return ""
    if lower == 0 and upper == -1:
        return "[*]"
    if lower == 1 and upper == -1:
        return "[+]"
    if lower == upper:
        return f"[{lower}]"
    return f"[{lower}..{'*' if upper == -1 else upper}]"


def to_emfatic(raw: dict[str, Any]) -> str:
    e = expand(raw)
    out = [f"@namespace(uri=\"{e['nsURI'] or 'http://modeler/' + e['package']}\", prefix=\"{e['nsPrefix'] or e['package']}\")",
           f"package {e['package']};", ""]
    for en, espec in e["enums"].items():
        lits = "; ".join(f"{lit['name']} = {i}" for i, lit in enumerate(espec["literals"]))
        out += [f"enum {en} {{ {lits}; }}", ""]
    for cname, c in e["classes"].items():
        if c.get("doc"):
            out.append(f"// {c['doc']}")
        head = ("abstract " if c["abstract"] else "") + f"class {cname}"
        if c["supertypes"]:
            head += " extends " + ", ".join(c["supertypes"])
        out.append(head + " {")
        for an, a in c["attributes"].items():
            flags = (("id " if a.get("id") else "") + ("derived " if a.get("derived") else "")
                     + ("readonly " if a.get("changeable") is False and not a.get("derived") else ""))
            d = a.get("default")
            dflt = "" if d is None else f" = {str(d).lower()}" if isinstance(d, bool) else f" = {d}" if isinstance(d, (int, float)) else f" = \"{d}\""
            allowed = f"  // in: {', '.join(a['in'])}" if a.get("in") else ""
            out.append(f"  {flags}attr {a['type']}{_mult(a['lower'], a['upper'])} {an}{dflt};{allowed}")
        for rn, r in c["references"].items():
            kw = "val" if r["containment"] else "ref"
            opp = f"#{r['opposite']}" if r.get("opposite") else ""
            out.append(f"  {kw} {r['type']}{_mult(r['lower'], r['upper'])}{opp} {rn};")
        out += ["}", ""]
    return "\n".join(out).rstrip() + "\n"


def _mermaid_mult(lower: int, upper: int) -> str:
    return f"{lower}..{'*' if upper == -1 else upper}" if not (lower == upper == 1) else "1"


def to_mermaid(raw: dict[str, Any]) -> str:
    e = expand(raw)
    lines = ["classDiagram"]
    for en, espec in e["enums"].items():
        lines.append(f"  class {en} {{")
        lines.append("    <<enumeration>>")
        lines += [f"    {lit['name']}" for lit in espec["literals"]]
        lines.append("  }")
    for cname, c in e["classes"].items():
        lines.append(f"  class {cname} {{")
        if c["abstract"]:
            lines.append("    <<abstract>>")
        for an, a in c["attributes"].items():
            lines.append(f"    {a['type']}{'[*]' if a['upper'] != 1 else ''} {an}")
        lines.append("  }")
        for s in c["supertypes"]:
            lines.append(f"  {s} <|-- {cname}")
    drawn: set[tuple[str, str]] = set()
    for cname, c in e["classes"].items():
        for rn, r in c["references"].items():
            if (cname, rn) in drawn:
                continue
            arrow = "*--" if r["containment"] else "-->"
            left = ""
            if r.get("opposite") and r["type"] in e["classes"]:
                o = e["classes"][r["type"]]["references"].get(r["opposite"])
                if o:
                    drawn.add((r["type"], r["opposite"]))
                    left = f"\"{_mermaid_mult(o['lower'], o['upper'])}\" "
                    arrow = "*--" if r["containment"] else ("--*" if o["containment"] else "--")
            lines.append(f"  {cname} {left}{arrow} \"{_mermaid_mult(r['lower'], r['upper'])}\" {r['type']} : {rn}")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# docs/DOMAIN.md: the domain explained (generated by `sync`, hand notes detected by `docs`)
# --------------------------------------------------------------------------- #
DOC_TEXT: dict[str, dict[str, str]] = {
    "it": {
        "title": "Dominio {package}",
        "note1": "Generato da `domain.ecore.yaml` con `npm run model:sync`: la struttura si cambia nel metamodello, non qui.",
        "note2": "Dettagli, vincoli e regole scritti a mano in questo file sono letti da `/modeler:metamodel` "
                 "e portati nel metamodello.",
        "diagram": "Diagramma", "rules": "Regole generali", "class_rules": "Regole", "attributes": "Attributi",
        "references": "Riferimenti", "enums": "Enum", "abstract": "Astratta.", "extends": "Estende {names}.",
        "name": "Nome", "type": "Tipo", "mult": "Molteplicità", "constraints": "Vincoli", "description": "Descrizione",
        "to": "Verso", "notes": "Note", "literal": "Letterale", "label": "Etichetta",
        "id": "identificativo", "unique": "unico", "default": "default {v}", "max_length": "max {n} caratteri",
        "min": "min {v}", "max": "max {v}", "readonly": "sola lettura", "derived": "calcolato", "containment": "contenimento",
        "opposite": "opposto `{name}`", "on_delete": "alla cancellazione: {v}",
        "required_from": "1 da {s}", "readonly_from": "sola lettura da {s}", "hidden_from": "assente da {s}", "in_from": "{v} da {s}",
    },
    "en": {
        "title": "Domain {package}",
        "note1": "Generated from `domain.ecore.yaml` by `npm run model:sync`: the structure changes in the metamodel, not here.",
        "note2": "Details, constraints and rules written by hand in this file are read by `/modeler:metamodel` "
                 "and moved into the metamodel.",
        "diagram": "Diagram", "rules": "General rules", "class_rules": "Rules", "attributes": "Attributes",
        "references": "References", "enums": "Enums", "abstract": "Abstract.", "extends": "Extends {names}.",
        "name": "Name", "type": "Type", "mult": "Multiplicity", "constraints": "Constraints", "description": "Description",
        "to": "To", "notes": "Notes", "literal": "Literal", "label": "Label",
        "id": "identifier", "unique": "unique", "default": "default {v}", "max_length": "max {n} characters",
        "min": "min {v}", "max": "max {v}", "readonly": "read only", "derived": "derived", "containment": "containment",
        "opposite": "opposite `{name}`", "on_delete": "on delete: {v}",
        "required_from": "1 from {s}", "readonly_from": "read only from {s}", "hidden_from": "hidden from {s}", "in_from": "{v} from {s}",
    },
}
MARKDOWN_MARK = "<!-- modeler: generated from domain.ecore.yaml by model:sync; checksum {checksum} -->"
_MARK_RE = re.compile(r"^<!-- modeler: generated from domain\.ecore\.yaml by model:sync; checksum ([0-9a-f]{12}) -->\s*$")
_TABLE_SEP_RE = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?$")


def _label(value: Any, lang: str) -> str:
    """A label written as a string or as {it: …, en: …}."""
    if isinstance(value, dict):
        return str(value.get(lang) or value.get("en") or value.get("it") or next(iter(value.values()), ""))
    return "" if value is None else str(value)


def _cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def _table(header: list[str], rows: list[list[Any]]) -> list[str]:
    return (["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
            + ["| " + " | ".join(_cell(c) for c in r) + " |" for r in rows])


def _literal_text(value: Any) -> str:
    return str(value).lower() if isinstance(value, bool) else str(value)


def _constraints(a: dict[str, Any], t: dict[str, str]) -> str:
    out = []
    if a.get("id"):
        out.append(t["id"])
    if a.get("unique"):
        out.append(t["unique"])
    if a.get("default") is not None:
        out.append(t["default"].format(v=_literal_text(a["default"])))
    if a.get("max_length"):
        out.append(t["max_length"].format(n=a["max_length"]))
    if a.get("min") is not None:
        out.append(t["min"].format(v=a["min"]))
    if a.get("max") is not None:
        out.append(t["max"].format(v=a["max"]))
    if a.get("derived"):
        out.append(t["derived"])
    elif a.get("changeable") is False:
        out.append(t["readonly"])
    return ", ".join(out)


def _ref_notes(r: dict[str, Any], t: dict[str, str]) -> str:
    out = []
    if r["containment"]:
        out.append(t["containment"])
    if r.get("opposite"):
        out.append(t["opposite"].format(name=r["opposite"]))
    if r.get("on_delete"):
        out.append(t["on_delete"].format(v=r["on_delete"]))
    if r.get("unique"):
        out.append(t["unique"])
    return ", ".join(out)


def _description(f: dict[str, Any]) -> str:
    doc = str(f.get("doc") or "")
    return f"{doc} ({f['help']})".strip() if f.get("help") else doc


def _state_notes(entries: list[dict[str, Any]] | None, t: dict[str, str], lang: str) -> tuple[str, str]:
    """What the workflow states add to a feature's row of DOMAIN.md: (multiplicity suffix, notes), from the entries
    of `behavior.domain_annotations` ({state, label, lower, readonly, hidden, in})."""
    mult, notes = [], []
    for x in entries or []:
        label = _label(x.get("label"), lang) or x["state"]
        if x.get("lower") == 1:
            mult.append(t["required_from"].format(s=label))
        if x.get("hidden"):
            notes.append(t["hidden_from"].format(s=label))
        elif x.get("readonly"):
            notes.append(t["readonly_from"].format(s=label))
        if x.get("in") is not None:
            notes.append(t["in_from"].format(v="{" + ", ".join(x["in"]) + "}", s=label))
    return ("".join(f" · {m}" for m in mult), ", ".join(notes))


def to_markdown(raw: dict[str, Any], lang: str | None = None, states: dict[str, Any] | None = None) -> str:
    """The domain explained: package, diagram, one section per class (attributes, references, rules), enums.
    Deterministic: the same metamodel always gives the same text (docs/DOMAIN.md is compared with it). `states`
    (`behavior.domain_annotations`: what the workflow states require, lock, hide or narrow per feature) adds
    «1 da <stato>» to the multiplicity and the rest to the constraints or notes."""
    e = expand(raw)
    lang = lang or e["language"]
    t = DOC_TEXT.get(lang) or DOC_TEXT["en"]
    states = states or {}

    def cells(cn: str, fn: str, static: str) -> tuple[str, str]:
        suffix, notes = _state_notes(states.get(cn, {}).get(fn), t, lang)
        return suffix, ", ".join(x for x in (static, notes) if x)

    def heading(name: str) -> str:
        spec = e["classes"].get(name) or e["enums"].get(name) or {}
        label = _label(spec.get("label"), lang)
        return f"{label} (`{name}`)" if label and label != name else name

    def display(name: str) -> str:
        return heading(name).split(" (`")[0]

    out = [f"# {t['title'].format(package=e['package'])}", ""]
    if e["doc"]:
        out += [str(e["doc"]), ""]
    out += [f"> {t['note1']}", f"> {t['note2']}", "", f"## {t['diagram']}", "", "```mermaid",
            to_mermaid(raw).rstrip("\n"), "```", ""]
    if e["rules"]:
        out += [f"## {t['rules']}", ""] + [f"- `{r['id']}`: {r['text']}" for r in e["rules"]] + [""]
    for cn, c in e["classes"].items():
        out += [f"## {heading(cn)}", ""]
        doc = str(c.get("doc") or "").strip()
        intro = [doc if doc.endswith((".", "!", "?")) else doc + "."] if doc else []
        if c["abstract"]:
            intro.append(f"*{t['abstract']}*")
        if c["supertypes"]:
            intro.append(t["extends"].format(names=", ".join(display(x) for x in c["supertypes"])))
        if intro:
            out += [" ".join(intro), ""]
        if c["attributes"]:
            rows = []
            for an, a in c["attributes"].items():
                suffix, cons = cells(cn, an, _constraints(a, t))
                rows.append([an, a["type"], _mermaid_mult(a["lower"], a["upper"]) + suffix, cons, _description(a)])
            out += [f"### {t['attributes']}", ""] + _table([t["name"], t["type"], t["mult"], t["constraints"], t["description"]], rows) + [""]
        if c["references"]:
            rows = []
            for rn, r in c["references"].items():
                suffix, notes = cells(cn, rn, _ref_notes(r, t))
                rows.append([rn, display(r["type"]) if r["type"] in e["classes"] else r["type"],
                             _mermaid_mult(r["lower"], r["upper"]) + suffix, notes, _description(r)])
            out += [f"### {t['references']}", ""] + _table([t["name"], t["to"], t["mult"], t["notes"], t["description"]], rows) + [""]
        if c.get("rules"):
            out += [f"### {t['class_rules']}", ""] + [f"- `{r['id']}`: {r['text']}" for r in c["rules"]] + [""]
    if e["enums"]:
        out += [f"## {t['enums']}", ""]
        for en, espec in e["enums"].items():
            rows = [[lit["name"], _label(lit.get("label"), lang)] for lit in espec["literals"]]
            out += [f"### {heading(en)}", ""] + _table([t["literal"], t["label"]], rows) + [""]
    return "\n".join(out).rstrip("\n") + "\n"


def markdown_normalize(text: str) -> str:
    """What a formatter or an editor may change is ignored: the marker line, table separator rows (with a pipe:
    a bare `---` is a thematic break and counts), spaces around pipes, line wrapping and blank lines.
    Two bullets and one bullet with the same words also compare equal: the price of ignoring the wrapping."""
    lines = []
    for line in text.splitlines():
        s = line.strip()
        if not s or _MARK_RE.match(s) or ("|" in s and _TABLE_SEP_RE.match(s)):
            continue
        lines.append(re.sub(r"\s*\|\s*", "|", s))
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def markdown_checksum(body: str) -> str:
    return hashlib.sha256(markdown_normalize(body).encode("utf-8")).hexdigest()[:12]


def markdown_document(raw: dict[str, Any], lang: str | None = None, states: dict[str, Any] | None = None) -> str:
    """What `sync` writes: the marker line (with the checksum of the body) and the body."""
    body = to_markdown(raw, lang, states)
    return MARKDOWN_MARK.format(checksum=markdown_checksum(body)) + "\n" + body


def markdown_split(text: str) -> tuple[str | None, str]:
    """(checksum of the marker line or None, body without it)."""
    first, _, rest = text.partition("\n")
    m = _MARK_RE.match(first)
    return (m.group(1), rest) if m else (None, text)


def markdown_sections(text: str) -> dict[str, str]:
    """The text split by headings: {"(intro)", "Persona", "Persona › Attributi", "Enum › Ruolo", …}, in order.
    Fenced blocks are not scanned; a repeated heading gets a " (2)" suffix."""
    out: dict[str, list[str]] = {"(intro)": []}
    cur, parent, fence = "(intro)", "", False
    for line in text.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            fence = not fence
        if not fence and (line.startswith("## ") or line.startswith("### ")):
            if line.startswith("## "):
                parent = line[3:].strip()
                name = parent
            else:
                name = f"{parent} › {line[4:].strip()}" if parent else line[4:].strip()
            cur, n = name, 2
            while cur in out:
                cur, n = f"{name} ({n})", n + 1
            if line.startswith("## "):
                parent = cur
            out[cur] = []
            continue
        out[cur].append(line)
    return {k: "\n".join(v) for k, v in out.items()}


def markdown_changes(generated: str, actual: str, limit: int = 12) -> list[dict[str, Any]]:
    """The sections of `actual` (the file on disk) that differ from `generated`, with a short diff each."""
    g = markdown_sections(markdown_split(generated)[1])
    a = markdown_sections(markdown_split(actual)[1])
    out = []
    for name in list(g) + [n for n in a if n not in g]:
        gs, as_ = g.get(name), a.get(name)
        if gs is not None and as_ is not None and markdown_normalize(gs) == markdown_normalize(as_):
            continue
        d = [x.rstrip() for x in list(difflib.unified_diff((gs or "").strip().splitlines(), (as_ or "").strip().splitlines(),
                                                           lineterm="", n=1))[2:] if not x.startswith("@@")]
        out.append({"name": name + (" (new)" if gs is None else " (missing)" if as_ is None else ""),
                    "diff": d[:limit] + (["…"] if len(d) > limit else [])})
    return out


def runtime_json(raw: dict[str, Any]) -> dict[str, Any]:
    """The metamodel as the web modeler reads it (canonical form + storage hints)."""
    e = expand(raw)
    e["datatypes"] = list(DATATYPES)
    e["builtin"] = sorted(BUILTIN_CLASSES)
    return e


def _rule_lines(prefix: str, old: Any, new: Any) -> list[str]:
    """`+ rule x`, `~ rule x changed`, `- rule x` (prefix "" for the package, "Persona: " for a class).
    The text is not printed: ids are stable and the text is in the file (and in docs/DOMAIN.md)."""
    o = {r.get("id"): r.get("text") for r in (old if isinstance(old, list) else []) if isinstance(r, dict)}
    n = {r.get("id"): r.get("text") for r in (new if isinstance(new, list) else []) if isinstance(r, dict)}
    out = [f"+ {prefix}rule {k}" for k in n if k not in o]
    out += [f"~ {prefix}rule {k} changed" for k in n if k in o and o[k] != n[k]]
    out += [f"- {prefix}rule {k}" for k in o if k not in n]
    return out


def diff(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    """Human-readable changes between two metamodels (for reviews and proposals)."""
    a, b = expand(old), expand(new)
    out: list[str] = []
    for en in b["enums"]:
        if en not in a["enums"]:
            out.append(f"+ enum {en}: {', '.join(lit['name'] for lit in b['enums'][en]['literals'])}")
        else:
            old_l = [lit["name"] for lit in a["enums"][en]["literals"]]
            new_l = [lit["name"] for lit in b["enums"][en]["literals"]]
            for n in new_l:
                if n not in old_l:
                    out.append(f"+ literal {en}.{n}")
            for n in old_l:
                if n not in new_l:
                    out.append(f"- literal {en}.{n}")
    for en in a["enums"]:
        if en not in b["enums"]:
            out.append(f"- enum {en}")
    out += _rule_lines("", a["rules"], b["rules"])
    for cn, c in b["classes"].items():
        if cn not in a["classes"]:
            out.append(f"+ class {cn}" + (" (abstract)" if c["abstract"] else "")
                       + (f" extends {', '.join(c['supertypes'])}" if c["supertypes"] else ""))
            for g in c.get("unique") or []:
                out.append(f"  + {cn}: unique ({', '.join(map(str, g))})")
            for an, at in c["attributes"].items():
                out.append(f"  + {cn}.{an}: {at['type']}{_mult(at['lower'], at['upper'])}")
            for rn, r in c["references"].items():
                out.append(f"  + {cn}.{rn} -> {r['type']}{_mult(r['lower'], r['upper'])}"
                           + (" containment" if r["containment"] else "") + (f" opposite {r['opposite']}" if r.get("opposite") else ""))
            for r in c.get("rules") or []:
                out.append(f"  + {cn}: rule {r.get('id') if isinstance(r, dict) else r}")
            continue
        oc = a["classes"][cn]
        if oc["abstract"] != c["abstract"]:
            out.append(f"~ class {cn}: abstract {oc['abstract']} -> {c['abstract']}")
        if oc["supertypes"] != c["supertypes"]:
            out.append(f"~ class {cn}: supertypes {oc['supertypes']} -> {c['supertypes']}")
        for g in c.get("unique") or []:
            if g not in (oc.get("unique") or []):
                out.append(f"+ {cn}: unique ({', '.join(map(str, g))})")
        for g in oc.get("unique") or []:
            if g not in (c.get("unique") or []):
                out.append(f"- {cn}: unique ({', '.join(map(str, g))})")
        out += _rule_lines(f"{cn}: ", oc.get("rules") or [], c.get("rules") or [])
        for kind in ("attributes", "references"):
            for fn, f in c[kind].items():
                renamed = f.get("renamed_from")
                of = oc[kind].get(fn) or (oc[kind].get(renamed) if renamed else None)
                if of is None:
                    out.append(f"+ {cn}.{fn}: {f['type']}{_mult(f['lower'], f['upper'])}")
                    continue
                if renamed and fn not in oc[kind]:
                    out.append(f"~ {cn}.{renamed} renamed to {fn}")
                for k in ("type", "lower", "upper", "containment", "opposite", "default", "id", "changeable", "derived"):
                    if of.get(k) != f.get(k):
                        out.append(f"~ {cn}.{fn}: {k} {of.get(k)} -> {f.get(k)}")
            for fn in oc[kind]:
                if fn not in c[kind] and not any(x.get("renamed_from") == fn for x in c[kind].values()):
                    out.append(f"- {cn}.{fn}")
    for cn in a["classes"]:
        if cn not in b["classes"]:
            out.append(f"- class {cn}")
    return out


# --------------------------------------------------------------------------- #
# Ecore XMI (interoperability with Eclipse EMF / Epsilon)
# --------------------------------------------------------------------------- #
ECORE_NS = "http://www.eclipse.org/emf/2002/Ecore"
XMI_NS = "http://www.omg.org/XMI"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
GENMODEL_SRC = "http://www.eclipse.org/emf/2002/GenModel"
MODELER_SRC = "modeler"
RULES_SRC = "rules"                    # domain rules: one detail per rule, id -> text


def _annot(parent: ET.Element, source: str, details: dict[str, Any]) -> None:
    details = {k: v for k, v in details.items() if v is not None and v != ""}
    if not details:
        return
    a = ET.SubElement(parent, "eAnnotations", {"source": source})
    for k, v in details.items():
        ET.SubElement(a, "details", {"key": k, "value": v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)})


def _rule_details(rules: Any) -> dict[str, Any]:
    return {r["id"]: r.get("text") for r in (rules if isinstance(rules, list) else []) if isinstance(r, dict) and "id" in r}


def _rules_from(el: ET.Element) -> list[dict[str, str]]:
    return [{"id": k, "text": v} for k, v in _details(el, RULES_SRC).items()]


def export_ecore(raw: dict[str, Any]) -> str:
    e = expand(raw)
    ET.register_namespace("xmi", XMI_NS)
    ET.register_namespace("xsi", XSI_NS)
    ET.register_namespace("ecore", ECORE_NS)
    root = ET.Element(f"{{{ECORE_NS}}}EPackage", {
        f"{{{XMI_NS}}}version": "2.0", "name": e["package"],
        "nsURI": e["nsURI"] or f"http://modeler/{e['package']}", "nsPrefix": e["nsPrefix"] or e["package"]})
    _annot(root, GENMODEL_SRC, {"documentation": e["doc"]})
    _annot(root, RULES_SRC, _rule_details(e["rules"]))
    xtype = f"{{{XSI_NS}}}type"

    def etype(t: str) -> str:
        if t in CUSTOM_DATATYPES or t in e["enums"] or t in e["classes"] or t in BUILTIN_CLASSES:
            return f"#//{t}"
        return f"ecore:EDataType {ECORE_NS}#//{t}"

    used_custom = sorted({a["type"] for c in e["classes"].values() for a in c["attributes"].values()
                          if a["type"] in CUSTOM_DATATYPES})
    uses_user = any(r["type"] in BUILTIN_CLASSES for c in e["classes"].values() for r in c["references"].values())
    for cname, c in e["classes"].items():
        el = ET.SubElement(root, "eClassifiers", {xtype: "ecore:EClass", "name": cname})
        if c["abstract"]:
            el.set("abstract", "true")
        if c["supertypes"]:
            el.set("eSuperTypes", " ".join(f"#//{s}" for s in c["supertypes"]))
        _annot(el, GENMODEL_SRC, {"documentation": c.get("doc")})
        _annot(el, MODELER_SRC, {k: c.get(k) for k in ("label", "plural", "table", "unique")})
        _annot(el, RULES_SRC, _rule_details(c.get("rules")))
        for an, a in c["attributes"].items():
            f = ET.SubElement(el, "eStructuralFeatures", {xtype: "ecore:EAttribute", "name": an, "eType": etype(a["type"])})
            if a["lower"]:
                f.set("lowerBound", str(a["lower"]))
            if a["upper"] != 1:
                f.set("upperBound", str(a["upper"]))
            if a.get("default") is not None:
                f.set("defaultValueLiteral", str(a["default"]).lower() if isinstance(a["default"], bool) else str(a["default"]))
            if a.get("id"):
                f.set("iD", "true")
            if a.get("changeable") is False:
                f.set("changeable", "false")
            if a.get("derived"):
                f.set("derived", "true")
            _annot(f, GENMODEL_SRC, {"documentation": a.get("doc")})
            _annot(f, MODELER_SRC, {k: a.get(k) for k in ("label", "help", "list", "min", "max", "max_length", "unique", "renamed_from")})
        for rn, r in c["references"].items():
            f = ET.SubElement(el, "eStructuralFeatures", {xtype: "ecore:EReference", "name": rn, "eType": f"#//{r['type']}"})
            if r["lower"]:
                f.set("lowerBound", str(r["lower"]))
            if r["upper"] != 1:
                f.set("upperBound", str(r["upper"]))
            if r["containment"]:
                f.set("containment", "true")
            if r.get("opposite"):
                f.set("eOpposite", f"#//{r['type']}/{r['opposite']}")
            _annot(f, GENMODEL_SRC, {"documentation": r.get("doc")})
            _annot(f, MODELER_SRC, {k: r.get(k) for k in ("label", "help", "list", "on_delete", "unique", "renamed_from")})
    for en, espec in e["enums"].items():
        el = ET.SubElement(root, "eClassifiers", {xtype: "ecore:EEnum", "name": en})
        _annot(el, MODELER_SRC, {"label": espec.get("label")})
        for i, lit in enumerate(espec["literals"]):
            le = ET.SubElement(el, "eLiterals", {"name": lit["name"], "value": str(i)})
            _annot(le, MODELER_SRC, {"label": lit.get("label")})
    for t in used_custom:
        ET.SubElement(root, "eClassifiers", {xtype: "ecore:EDataType", "name": t, "instanceClassName": CUSTOM_DATATYPES[t]})
    if uses_user:
        u = ET.SubElement(root, "eClassifiers", {xtype: "ecore:EClass", "name": "User"})
        _annot(u, MODELER_SRC, {"builtin": "true"})
        ET.SubElement(u, "eStructuralFeatures", {xtype: "ecore:EAttribute", "name": "email",
                                                 "eType": f"ecore:EDataType {ECORE_NS}#//EString"})
    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def _details(el: ET.Element, source: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for a in el.findall("eAnnotations"):
        if a.get("source") == source:
            for d in a.findall("details"):
                v: Any = d.get("value", "")
                if source == MODELER_SRC and d.get("key") not in ("renamed_from",):
                    try:
                        v = json.loads(v) if v and (v[0] in "{[" or v in ("true", "false") or re.match(r"^-?\d+(\.\d+)?$", v)) else v
                    except ValueError:
                        pass
                out[d.get("key")] = v
    return out


def import_ecore(text: str) -> dict[str, Any]:
    """Reads an .ecore file (as written by Eclipse or by export_ecore) into the YAML notation."""
    root = ET.fromstring(text)
    if not root.tag.endswith("EPackage"):
        raise M.ModelError("not an Ecore EPackage")
    xtype = f"{{{XSI_NS}}}type"
    raw: dict[str, Any] = {"package": root.get("name") or "domain", "nsURI": root.get("nsURI", ""),
                           "nsPrefix": root.get("nsPrefix", ""), "classes": {}, "enums": {}}
    doc = _details(root, GENMODEL_SRC).get("documentation")
    if doc:
        raw["doc"] = doc
    if _rules_from(root):
        raw["rules"] = _rules_from(root)

    def tname(ref: str | None) -> str:
        return (ref or "EString").split("#//")[-1]

    for cl in root.findall("eClassifiers"):
        kind = (cl.get(xtype) or "").split(":")[-1]
        name = cl.get("name")
        if kind == "EClass":
            if _details(cl, MODELER_SRC).get("builtin"):
                continue
            c: dict[str, Any] = {}
            if cl.get("abstract") == "true" or cl.get("interface") == "true":
                c["abstract"] = True
            if cl.get("eSuperTypes"):
                c["supertypes"] = [tname(s) for s in cl.get("eSuperTypes", "").split()]
            if _details(cl, GENMODEL_SRC).get("documentation"):
                c["doc"] = _details(cl, GENMODEL_SRC)["documentation"]
            c.update(_details(cl, MODELER_SRC))
            attrs: dict[str, Any] = {}
            refs: dict[str, Any] = {}
            for f in cl.findall("eStructuralFeatures"):
                fk = (f.get(xtype) or "").split(":")[-1]
                spec: dict[str, Any] = {"type": tname(f.get("eType") or f.get("eGenericType"))}
                if f.get("lowerBound"):
                    spec["lower"] = int(f.get("lowerBound"))
                if f.get("upperBound"):
                    spec["upper"] = int(f.get("upperBound"))
                if _details(f, GENMODEL_SRC).get("documentation"):
                    spec["doc"] = _details(f, GENMODEL_SRC)["documentation"]
                spec.update(_details(f, MODELER_SRC))
                if fk == "EAttribute":
                    if f.get("defaultValueLiteral") is not None:
                        d: Any = f.get("defaultValueLiteral")
                        if spec["type"] == "EBoolean":
                            d = d == "true"
                        elif spec["type"] in ("EInt", "ELong", "EShort", "EBigInteger") and re.match(r"^-?\d+$", d):
                            d = int(d)
                        elif spec["type"] in ("EDouble", "EFloat", "EBigDecimal", "Money") and re.match(r"^-?\d+(\.\d+)?$", d):
                            d = float(d) if "." in d else int(d)
                        spec["default"] = d
                    if f.get("iD") == "true":
                        spec["id"] = True
                    if f.get("changeable") == "false":
                        spec["changeable"] = False
                    if f.get("derived") == "true":
                        spec["derived"] = True
                    attrs[f.get("name")] = spec
                else:
                    if f.get("containment") == "true":
                        spec["containment"] = True
                    if f.get("eOpposite"):
                        spec["opposite"] = f.get("eOpposite", "").split("/")[-1]
                    refs[f.get("name")] = spec
            if attrs:
                c["attributes"] = attrs
            if refs:
                c["references"] = refs
            if _rules_from(cl):
                c["rules"] = _rules_from(cl)
            raw["classes"][name] = c
        elif kind == "EEnum":
            lits = []
            for lit in cl.findall("eLiterals"):
                lab = _details(lit, MODELER_SRC).get("label")
                lits.append({"name": lit.get("name"), "label": lab} if lab is not None else lit.get("name"))
            lab = _details(cl, MODELER_SRC).get("label")
            raw["enums"][name] = {"label": lab, "literals": lits} if lab else lits
    return compact(raw)


# --------------------------------------------------------------------------- #
# Proposals from the web modeler
# --------------------------------------------------------------------------- #
def from_editor(doc: dict[str, Any]) -> dict[str, Any]:
    """The editor works on the canonical form (runtime_json): back to compact YAML structure."""
    doc = {k: v for k, v in doc.items() if k in TOP_KEYS}   # drops datatypes and builtin
    return compact(doc)
