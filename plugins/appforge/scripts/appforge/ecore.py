"""The domain metamodel in Ecore notation (`domain.ecore.yaml`).

An application is described by two files, as in EMF (.ecore + .genmodel):

* `domain.ecore.yaml` - the metamodel: package, classes (abstract, supertypes),
  attributes, references (containment, multiplicity, opposite), enums. It says
  *what* the domain is and is the file edited from the prompt, by the web modeler
  in the admin area, or derived from an existing database (`reverse`).
* `app.yaml` - how the application behaves: app settings, roles, permissions,
  workflows, events, reactions. Its `entities:` section only adds behaviour to
  the classes of the metamodel (no `fields`).

`compose()` turns the pair into the appforge model understood by the generators;
`extract()` does the opposite for a legacy single-file `app.yaml`.
"""

from __future__ import annotations

import copy
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from . import model as M

METAMODEL_FILE = "domain.ecore.yaml"
CLASS_NAME = re.compile(r"^[A-Z][A-Za-z0-9]{1,39}$")
FEATURE_NAME = re.compile(r"^[a-z][A-Za-z0-9_]{0,39}$")
LITERAL_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,39}$")
BUILTIN_CLASSES = {"User"}          # application users (table `profiles`): referenced, never declared

# Ecore data types and the appforge field type they map to.
DATATYPES: dict[str, str] = {
    "EString": "string", "EInt": "int", "ELong": "int", "EShort": "int", "EBigInteger": "int",
    "EDouble": "number", "EFloat": "number", "EBigDecimal": "number", "EBoolean": "bool",
    "EDate": "datetime", "Text": "text", "Email": "email", "URL": "url", "Money": "money",
    "Date": "date", "DateTime": "datetime", "JSON": "json",
}
# appforge field type -> preferred data type (used by extract and reverse)
TYPE_TO_DATATYPE = {
    "string": "EString", "text": "Text", "email": "Email", "url": "URL", "int": "EInt", "number": "EDouble",
    "money": "Money", "bool": "EBoolean", "date": "Date", "datetime": "EDate", "json": "JSON",
}
# custom data types declared in the exported .ecore (instance classes for Java tools)
CUSTOM_DATATYPES = {"Text": "java.lang.String", "Email": "java.lang.String", "URL": "java.lang.String",
                    "Money": "java.math.BigDecimal", "Date": "java.time.LocalDate",
                    "DateTime": "java.util.Date", "JSON": "java.lang.String"}

CLASS_KEYS = {"abstract", "supertypes", "doc", "label", "plural", "table", "attributes", "references"}
ATTRIBUTE_KEYS = {"type", "lower", "upper", "default", "id", "unique", "changeable", "doc", "label", "help",
                  "list", "min", "max", "max_length", "renamed_from", "column"}
REFERENCE_KEYS = {"type", "lower", "upper", "containment", "opposite", "doc", "label", "help", "list",
                  "on_delete", "unique", "renamed_from", "column", "join_table"}
BEHAVIOUR_KEYS = {"kind", "code_prefix", "display", "scope_field", "icon", "menu", "order", "description",
                  "indexes", "permissions", "workflow", "label", "plural", "table", "ui"}
TOP_KEYS = {"package", "nsURI", "nsPrefix", "doc", "language", "classes", "enums", "diagram"}
LANGUAGES = {"en", "it"}


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
        "diagram": copy.deepcopy(raw.get("diagram") or {}),
    }
    for cname, cspec in (raw.get("classes") or {}).items():
        cspec = cspec if isinstance(cspec, dict) else {}
        cls: dict[str, Any] = {k: copy.deepcopy(v) for k, v in cspec.items() if k not in ("attributes", "references")}
        cls["abstract"] = bool(cspec.get("abstract", False))
        sup = cspec.get("supertypes") or []
        cls["supertypes"] = [str(s) for s in (sup if isinstance(sup, list) else [sup])]
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
        for k in ("abstract", "supertypes", "doc", "label", "plural", "table"):
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
    header = ("# Domain metamodel (Ecore notation). Edit it from the prompt (/appforge:metamodel),\n"
              "# in the modeler (admin area or /appforge:studio) or by hand; behaviour lives in app.yaml.\n")
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
            text += ("\n" if key in ("enums", "diagram") else "") + f"{key}:\n" + "".join(
                "  " + line + "\n" for line in body_text.rstrip("\n").split("\n"))
    return header + text


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
                  "(behaviour such as app, roles, reactions goes in app.yaml)")
    e = expand(raw)
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
        behaviour = extra & BEHAVIOUR_KEYS
        if behaviour:
            rep.error(where, f"{', '.join(sorted(behaviour))}: behaviour, declare it under entities.{cname} in app.yaml")
        if extra - behaviour:
            rep.error(where, f"unknown keys: {', '.join(sorted(extra - behaviour))}")
        for s in c["supertypes"]:
            if s not in e["classes"]:
                rep.error(where, f"unknown supertype '{s}'")
        _all_supertypes(e, cname, rep)
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
    # inherited name clashes and flattening problems are found by composing
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
    return rep


def _check_feature_name(name: str, where: str, rep: M.Report) -> None:
    if not FEATURE_NAME.match(name):
        rep.error(where, "feature names start lowercase (camelCase or snake_case)")
        return
    col = M.snake(name)
    if col in M.RESERVED_FIELDS:
        rep.error(where, f"'{name}' is a standard column ({col}): rename it")


# --------------------------------------------------------------------------- #
# Composition: metamodel + behaviour -> appforge model
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


def default_plural_label(label: str, language: str) -> str:
    words = label.split(" ")
    if language == "it":
        words[0] = plural_word(words[0], "it")
    else:
        words[-1] = M.pluralize(words[-1])
    return " ".join(words)


def field_key(feature: str, spec: dict[str, Any] | None = None) -> str:
    """Stored column of a feature: `column` if given (adopted databases), else snake_case of the name."""
    if spec and spec.get("column"):
        return str(spec["column"])
    return M.snake(feature)


def literal_key(name: str) -> str:
    """Enum literal -> stored value: ADMIN, inProgress, IN_PROGRESS -> admin, in_progress, in_progress."""
    return M.snake(name).lower()


def _attribute_field(e: dict[str, Any], a: dict[str, Any]) -> dict[str, Any]:
    t = str(a["type"])
    if a["upper"] != 1:
        f: dict[str, Any] = {"type": "json"}
    elif t in e["enums"]:
        f = {"type": "enum", "enum": t}
        if a.get("default") is not None:
            f["default"] = literal_key(str(a["default"]))
    else:
        f = {"type": DATATYPES.get(t, "string")}
    if a["lower"] >= 1:
        f["required"] = True
    if a.get("id") or a.get("unique"):
        f["unique"] = True
    if a.get("changeable") is False:
        f["readonly"] = True
    for k in ("default", "label", "help", "list", "min", "max", "max_length", "renamed_from"):
        if a.get(k) is not None and k not in f:
            f[k] = a[k] if k != "renamed_from" else field_key(str(a[k]))
    return f


def _ref_field(target: str, required: bool, r: dict[str, Any], **extra: Any) -> dict[str, Any]:
    f: dict[str, Any] = {"type": "ref", "to": target}
    if required:
        f["required"] = True
    for k in ("label", "help", "list"):
        if r.get(k) is not None:
            f[k] = r[k]
    if r.get("renamed_from"):
        f["renamed_from"] = field_key(str(r["renamed_from"]))
    f.update({k: v for k, v in extra.items() if v is not None})
    return f


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


def compose(meta: dict[str, Any], behaviour: dict[str, Any] | None, rep: M.Report | None = None) -> dict[str, Any]:
    """appforge raw model from a metamodel and the behaviour file. Problems go to `rep`."""
    rep = rep if rep is not None else M.Report()
    beh = copy.deepcopy(behaviour or {})
    e = expand(meta)
    raw: dict[str, Any] = {k: v for k, v in beh.items() if k not in ("entities", "enums")}
    raw.setdefault("app", {})
    if beh.get("enums"):
        rep.error("app.yaml enums", "enums belong to the metamodel (domain.ecore.yaml)")
    enums: dict[str, Any] = {}
    for en, espec in e["enums"].items():
        values = [{"key": literal_key(lit["name"]),
                   "label": lit["label"] if lit.get("label") is not None else M.humanize(literal_key(lit["name"]))}
                  for lit in espec["literals"]]
        enums[en] = {"values": values, **({"label": espec["label"]} if espec.get("label") else {})}
    raw["enums"] = enums
    beh_entities = beh.get("entities") or {}
    for name, spec in beh_entities.items():
        where = f"app.yaml entities.{name}"
        if name not in e["classes"]:
            rep.error(where, "not a class of the metamodel")
        elif e["classes"][name]["abstract"]:
            rep.error(where, "abstract classes have no records: add the behaviour to a concrete subclass")
        if isinstance(spec, dict):
            if "fields" in spec:
                rep.error(where, "fields are declared in the metamodel (attributes / references)")
            bad = set(spec) - BEHAVIOUR_KEYS
            if bad:
                rep.error(where, f"unknown keys: {', '.join(sorted(bad))}")
    columns = reference_columns(e)
    entities: dict[str, Any] = {}
    for cname, c in e["classes"].items():
        if c["abstract"] or cname in BUILTIN_CLASSES:
            continue
        ent: dict[str, Any] = {}
        for k_meta, k_ent in (("label", "label"), ("plural", "plural"), ("table", "table"), ("doc", "description")):
            if c.get(k_meta):
                ent[k_ent] = c[k_meta]
        if e["language"] == "it":
            ent.setdefault("table", default_table(cname, "it"))
            if "plural" not in ent:
                lab = c.get("label") or M.humanize(cname)
                ent["plural"] = ({k: default_plural_label(v, "it" if k == "it" else "en") for k, v in lab.items()}
                                 if isinstance(lab, dict) else default_plural_label(lab, "it"))
        fields: dict[str, Any] = {}
        attrs, _ = features(e, cname)
        for an, a in attrs.items():
            fields[field_key(an, a)] = _attribute_field(e, a)
        for col in columns:
            if col["holder"] != cname:
                continue
            key = col["field"]
            if key in fields:
                rep.error(f"classes.{cname}", f"'{key}' is both an attribute and a reference column")
                continue
            fields[key] = _ref_field(col["target"], col["required"], col["spec"],
                                     many=True if col["many"] else None,
                                     on_delete=col["on_delete"],
                                     unique=True if col["unique"] and not col["many"] else None)
        ent["fields"] = fields
        id_attr = next((field_key(n, a) for n, a in attrs.items() if a.get("id")), None)
        spec = beh_entities.get(cname) if isinstance(beh_entities.get(cname), dict) else {}
        for k, v in spec.items():
            if k != "fields":
                ent[k] = copy.deepcopy(v)
        if id_attr and "display" not in ent:
            ent["display"] = id_attr
        entities[cname] = ent
    raw["entities"] = entities
    return raw


def extract(raw: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Splits a legacy single-file app.yaml into (metamodel, behaviour)."""
    norm = M.normalize(raw)
    meta: dict[str, Any] = {"package": re.sub(r"[^a-z0-9_]", "_", str(norm["app"]["slug"]).replace("-", "_")),
                            "classes": {}, "enums": {}}
    for en, espec in (raw.get("enums") or {}).items():
        nspec = norm["enums"][en]
        literals: list[Any] = []
        for v in nspec["values"]:
            orig = None
            for src in (espec if isinstance(espec, list) else (espec or {}).get("values") or []):
                key = src.get("key") if isinstance(src, dict) and "key" in src else (next(iter(src)) if isinstance(src, dict) else src)
                if str(key) == v["key"]:
                    orig = src
            lab = None
            if isinstance(orig, dict):
                lab = orig.get("label") if "key" in orig else next(iter(orig.values()))
            elif isinstance(espec, dict) and (espec.get("labels") or {}).get(v["key"]) is not None:
                lab = espec["labels"][v["key"]]
            literals.append({"name": v["key"], "label": lab} if lab is not None else v["key"])
        label = espec.get("label") if isinstance(espec, dict) else None
        meta["enums"][en] = {"label": label, "literals": literals} if label else literals
    beh = {k: copy.deepcopy(v) for k, v in raw.items() if k not in ("entities", "enums")}
    beh_entities: dict[str, Any] = {}
    for name, spec in (raw.get("entities") or {}).items():
        spec = spec or {}
        nent = norm["entities"][name]
        cls: dict[str, Any] = {}
        for k_ent, k_meta in (("label", "label"), ("plural", "plural"), ("table", "table"), ("description", "doc")):
            if spec.get(k_ent):
                cls[k_meta] = spec[k_ent]
        attrs: dict[str, Any] = {}
        refs: dict[str, Any] = {}
        for fkey, fspec in (spec.get("fields") or {}).items():
            fspec = {"type": fspec} if isinstance(fspec, str) else dict(fspec or {})
            fname = _feature_name(fkey)
            t = fspec.get("type", "string")
            if t == "ref":
                r: dict[str, Any] = {"type": fspec["to"]}
                if fspec.get("many"):
                    r["upper"] = -1
                if fspec.get("required"):
                    r["lower"] = 1
                for k in ("on_delete", "label", "help", "unique"):
                    if fspec.get(k) is not None:
                        r[k] = fspec[k]
                if fspec.get("renamed_from"):
                    r["renamed_from"] = _feature_name(fspec["renamed_from"])
                refs[fname] = r
            else:
                a: dict[str, Any] = {"type": fspec["enum"] if t == "enum" else TYPE_TO_DATATYPE.get(t, "EString")}
                if fspec.get("required"):
                    a["lower"] = 1
                if fspec.get("unique"):
                    a["unique"] = True
                if fspec.get("readonly"):
                    a["changeable"] = False
                for k in ("default", "label", "help", "min", "max", "max_length"):
                    if fspec.get(k) is not None:
                        a[k] = fspec[k]
                if fspec.get("renamed_from"):
                    a["renamed_from"] = _feature_name(fspec["renamed_from"])
                attrs[fname] = a
        # keep the list columns of the legacy model (the new order puts attributes first)
        new_order = list(attrs) + list(refs)
        for pos, fname in enumerate(new_order):
            target = attrs.get(fname) if fname in attrs else refs[fname]
            legacy = nent["fields"][field_key(fname) if field_key(fname) in nent["fields"] else fname]["list"]
            if legacy != (pos < 4):
                target["list"] = legacy
        if attrs:
            cls["attributes"] = attrs
        if refs:
            cls["references"] = refs
        meta["classes"][name] = cls
        rest = {k: copy.deepcopy(v) for k, v in spec.items() if k not in ("fields", "label", "plural", "table", "description")}
        if rest:
            beh_entities[name] = rest
    if beh_entities:
        beh["entities"] = beh_entities
    if not meta["enums"]:
        meta.pop("enums")
    return compact(meta), beh


def _feature_name(key: str) -> str:
    """snake_case column -> camelCase feature, unless that does not map back to the same column."""
    parts = str(key).split("_")
    camel = parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:])
    return camel if M.snake(camel) == key and FEATURE_NAME.match(camel) else str(key)


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
    out = [f"@namespace(uri=\"{e['nsURI'] or 'http://appforge/' + e['package']}\", prefix=\"{e['nsPrefix'] or e['package']}\")",
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
            flags = ("id " if a.get("id") else "") + ("readonly " if a.get("changeable") is False else "")
            d = a.get("default")
            dflt = "" if d is None else f" = {str(d).lower()}" if isinstance(d, bool) else f" = {d}" if isinstance(d, (int, float)) else f" = \"{d}\""
            out.append(f"  {flags}attr {a['type']}{_mult(a['lower'], a['upper'])} {an}{dflt};")
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


def runtime_json(raw: dict[str, Any]) -> dict[str, Any]:
    """The metamodel as the web modeler reads it (canonical form + storage hints)."""
    e = expand(raw)
    e["datatypes"] = list(DATATYPES)
    e["builtin"] = sorted(BUILTIN_CLASSES)
    return e


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
    for cn, c in b["classes"].items():
        if cn not in a["classes"]:
            out.append(f"+ class {cn}" + (" (abstract)" if c["abstract"] else "")
                       + (f" extends {', '.join(c['supertypes'])}" if c["supertypes"] else ""))
            for an, at in c["attributes"].items():
                out.append(f"  + {cn}.{an}: {at['type']}{_mult(at['lower'], at['upper'])}")
            for rn, r in c["references"].items():
                out.append(f"  + {cn}.{rn} -> {r['type']}{_mult(r['lower'], r['upper'])}"
                           + (" containment" if r["containment"] else "") + (f" opposite {r['opposite']}" if r.get("opposite") else ""))
            continue
        oc = a["classes"][cn]
        if oc["abstract"] != c["abstract"]:
            out.append(f"~ class {cn}: abstract {oc['abstract']} -> {c['abstract']}")
        if oc["supertypes"] != c["supertypes"]:
            out.append(f"~ class {cn}: supertypes {oc['supertypes']} -> {c['supertypes']}")
        for kind in ("attributes", "references"):
            for fn, f in c[kind].items():
                renamed = f.get("renamed_from")
                of = oc[kind].get(fn) or (oc[kind].get(renamed) if renamed else None)
                if of is None:
                    out.append(f"+ {cn}.{fn}: {f['type']}{_mult(f['lower'], f['upper'])}")
                    continue
                if renamed and fn not in oc[kind]:
                    out.append(f"~ {cn}.{renamed} renamed to {fn}")
                for k in ("type", "lower", "upper", "containment", "opposite", "default", "id", "changeable"):
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
APPFORGE_SRC = "appforge"


def _annot(parent: ET.Element, source: str, details: dict[str, Any]) -> None:
    details = {k: v for k, v in details.items() if v is not None and v != ""}
    if not details:
        return
    a = ET.SubElement(parent, "eAnnotations", {"source": source})
    for k, v in details.items():
        ET.SubElement(a, "details", {"key": k, "value": v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)})


def export_ecore(raw: dict[str, Any]) -> str:
    e = expand(raw)
    ET.register_namespace("xmi", XMI_NS)
    ET.register_namespace("xsi", XSI_NS)
    ET.register_namespace("ecore", ECORE_NS)
    root = ET.Element(f"{{{ECORE_NS}}}EPackage", {
        f"{{{XMI_NS}}}version": "2.0", "name": e["package"],
        "nsURI": e["nsURI"] or f"http://appforge/{e['package']}", "nsPrefix": e["nsPrefix"] or e["package"]})
    _annot(root, GENMODEL_SRC, {"documentation": e["doc"]})
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
        _annot(el, APPFORGE_SRC, {k: c.get(k) for k in ("label", "plural", "table")})
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
            _annot(f, GENMODEL_SRC, {"documentation": a.get("doc")})
            _annot(f, APPFORGE_SRC, {k: a.get(k) for k in ("label", "help", "list", "min", "max", "max_length", "unique", "renamed_from")})
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
            _annot(f, APPFORGE_SRC, {k: r.get(k) for k in ("label", "help", "list", "on_delete", "unique", "renamed_from")})
    for en, espec in e["enums"].items():
        el = ET.SubElement(root, "eClassifiers", {xtype: "ecore:EEnum", "name": en})
        _annot(el, APPFORGE_SRC, {"label": espec.get("label")})
        for i, lit in enumerate(espec["literals"]):
            le = ET.SubElement(el, "eLiterals", {"name": lit["name"], "value": str(i)})
            _annot(le, APPFORGE_SRC, {"label": lit.get("label")})
    for t in used_custom:
        ET.SubElement(root, "eClassifiers", {xtype: "ecore:EDataType", "name": t, "instanceClassName": CUSTOM_DATATYPES[t]})
    if uses_user:
        u = ET.SubElement(root, "eClassifiers", {xtype: "ecore:EClass", "name": "User"})
        _annot(u, APPFORGE_SRC, {"builtin": "true"})
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
                if source == APPFORGE_SRC and d.get("key") not in ("renamed_from",):
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

    def tname(ref: str | None) -> str:
        return (ref or "EString").split("#//")[-1]

    for cl in root.findall("eClassifiers"):
        kind = (cl.get(xtype) or "").split(":")[-1]
        name = cl.get("name")
        if kind == "EClass":
            if _details(cl, APPFORGE_SRC).get("builtin"):
                continue
            c: dict[str, Any] = {}
            if cl.get("abstract") == "true" or cl.get("interface") == "true":
                c["abstract"] = True
            if cl.get("eSuperTypes"):
                c["supertypes"] = [tname(s) for s in cl.get("eSuperTypes", "").split()]
            if _details(cl, GENMODEL_SRC).get("documentation"):
                c["doc"] = _details(cl, GENMODEL_SRC)["documentation"]
            c.update(_details(cl, APPFORGE_SRC))
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
                spec.update(_details(f, APPFORGE_SRC))
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
            raw["classes"][name] = c
        elif kind == "EEnum":
            lits = []
            for lit in cl.findall("eLiterals"):
                lab = _details(lit, APPFORGE_SRC).get("label")
                lits.append({"name": lit.get("name"), "label": lab} if lab is not None else lit.get("name"))
            lab = _details(cl, APPFORGE_SRC).get("label")
            raw["enums"][name] = {"label": lab, "literals": lits} if lab else lits
    return compact(raw)


# --------------------------------------------------------------------------- #
# Proposals from the web modeler
# --------------------------------------------------------------------------- #
def from_editor(doc: dict[str, Any]) -> dict[str, Any]:
    """The editor works on the canonical form (runtime_json): back to compact YAML structure."""
    doc = {k: v for k, v in doc.items() if k in TOP_KEYS}   # drops datatypes, builtin, behaviour
    return compact(doc)


# --------------------------------------------------------------------------- #
# Behaviour linked to the metamodel (shown by the modeler)
# --------------------------------------------------------------------------- #
def _clause_fields(clauses: Any) -> list[str]:
    return [str(c.get("field")) for c in M._as_list(clauses) if isinstance(c, dict) and c.get("field")]


def behaviour_summary(m: dict[str, Any]) -> dict[str, Any]:
    """What app.yaml attaches to each class: workflow, events, reactions, webhooks, UI, and which
    features the behaviour uses (so the modeler can warn before they are removed or renamed)."""
    loc = m["app"]["locales"][0]
    events = M.all_events(m)
    classes: dict[str, Any] = {}
    for name, e in m["entities"].items():
        uses: dict[str, list[str]] = {}

        def use(field: str | None, where: str) -> None:
            if field and field in e["fields"]:
                uses.setdefault(field, [])
                if where not in uses[field]:
                    uses[field].append(where)

        use(e["display"], "display")
        use(e["scope_field"], "scope")
        for ix in e["indexes"]:
            for c in ix:
                use(c, "index")
        for action, principals in e["permissions"].items():
            for p in principals:
                if p.startswith("field:"):
                    use(p[6:], f"permission {action}")
        wf = None
        if e["workflow"]:
            for sk, st in e["workflow"]["states"].items():
                for p in st["owner"] + st["editable_by"]:
                    if p.startswith("field:"):
                        use(p[6:], f"state {sk}")
            trans = []
            for tk, tr in e["workflow"]["transitions"].items():
                for f in _clause_fields(tr["guard"]) + _clause_fields(tr["condition"]):
                    use(f, f"transition {tk}")
                if tr["trigger"]["kind"] == "timed":
                    at = M.parse_offset(tr["trigger"].get("at") or "")
                    use(at[0] if at else None, f"timed transition {tk}")
                for p in tr["by"]:
                    if p.startswith("field:"):
                        use(p[6:], f"transition {tk}")
                trans.append({"key": tk, "label": tr["label"][loc], "from": tr["from"], "to": tr["to"], "by": tr["by"],
                              "trigger": tr["trigger"]["kind"],
                              "guard": [f"{c.get('field')} {c.get('op')} {c.get('value', '')}".strip() for c in tr["guard"] if isinstance(c, dict)],
                              "emits": tr["emits"]})
            wf = {"states": [{"key": k, "label": s["label"][loc], "kind": s["kind"], "color": s["color"]}
                             for k, s in e["workflow"]["states"].items()],
                  "transitions": trans}
        ui = e.get("ui") or {}
        for k in ("calendar", "cards"):
            for f in (ui.get(k) or {}).values():
                use(f if isinstance(f, str) else None, f"ui {k}")
        if ui.get("kanban"):
            use(ui["kanban"].get("group_by"), "ui kanban")
        own_events = sorted(t for t, ev in events.items() if ev.get("entity") == name)
        reactions = []
        for r in m["reactions"]:
            ev = events.get(str(r.get("on")))
            if ev and ev.get("entity") == name:
                reactions.append({"name": r["name"], "on": r["on"], "do": r.get("do")})
                when = r.get("when") or {}
                for f in _clause_fields(when.get("clauses")):
                    use(f, f"reaction {r['name']}")
                for f in (r.get("set") or {}) if isinstance(r.get("set"), dict) else []:
                    use(f, f"reaction {r['name']}")
                at = M.parse_offset(str(r.get("at", ""))) if r.get("do") == "schedule" else None
                use(at[0] if at else None, f"reaction {r['name']}")
        hooks = sorted({s["name"] for s in m["subscriptions"] for t in own_events
                        if any(p == "*" or M._glob(p, t) for p in s["events"])})
        classes[name] = {"kind": e["kind"], "workflow": wf, "events": own_events, "reactions": reactions,
                         "webhooks": hooks, "views": ui.get("views", ["table"]), "uses": uses}
    return {"app": {"name": m["app"]["name"], "slug": m["app"]["slug"]}, "classes": classes,
            "subscriptions": [{"name": s["name"], "events": s["events"]} for s in m["subscriptions"]]}
