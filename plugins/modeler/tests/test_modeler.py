"""Metamodel notation, storage mapping, the modeler installed in an app, proposals, reverse and drift.

python3 -m unittest discover -s plugins/modeler/tests   (MODELER_PG=postgresql://… enables the database tests)
"""

import argparse
import contextlib
import copy
import difflib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from metamodel import __version__  # noqa: E402
from metamodel import cli  # noqa: E402
from metamodel import dbschema as D  # noqa: E402
from metamodel import behavior as B  # noqa: E402
from metamodel import ecore as E  # noqa: E402
from metamodel import sqlgen as G  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "anagrafica.ecore.yaml"


class NotationTests(unittest.TestCase):
    def test_fixture_is_valid_and_round_trips(self):
        meta = E.load(FIXTURE)
        self.assertTrue(E.validate(meta).ok, E.validate(meta).render())
        self.assertEqual(E.expand(E.loads(E.dumps(meta))), E.expand(meta))
        back = E.expand(E.import_ecore(E.export_ecore(meta)))
        self.assertEqual(back["classes"], E.expand(meta)["classes"])
        self.assertEqual(back["enums"], E.expand(meta)["enums"])
        self.assertEqual(back["rules"], E.expand(meta)["rules"])
        self.assertEqual(E.expand(E.from_editor(E.runtime_json(meta)))["rules"], E.expand(meta)["rules"])   # editor keeps them

    def test_rules_validation(self):
        base = E.load(FIXTURE)

        def errors(change):
            m = copy.deepcopy(base)
            change(m)
            return E.validate(m).render()
        self.assertIn("a list of {id, text}", errors(lambda m: m.__setitem__("rules", "x")))
        self.assertIn("lowercase identifier", errors(lambda m: m.__setitem__("rules", [{"id": "No-Overlap", "text": "t"}])))
        self.assertIn("text: the rule", errors(lambda m: m.__setitem__("rules", [{"id": "a"}])))
        self.assertIn("declared twice", errors(lambda m: m.__setitem__("rules", [{"id": "a", "text": "t"}, {"id": "a", "text": "u"}])))
        self.assertIn("unknown keys: when", errors(lambda m: m.__setitem__("rules", [{"id": "a", "text": "t", "when": 1}])))
        self.assertIn("classes.Persona.rules[0]", errors(lambda m: m["classes"]["Persona"].__setitem__("rules", ["no"])))
        self.assertTrue(E.validate(base).ok)
        c = E.compact(base)
        self.assertEqual(c["rules"], [{"id": "email_unica", "text": "Un account per persona con email unica nel sistema"}])
        self.assertEqual(list(c["classes"]["Persona"])[-1], "rules")                       # after references
        self.assertEqual(list(c)[-1], "rules")                                             # after enums

    def test_diff_shows_rules(self):
        old = E.load(FIXTURE)
        new = copy.deepcopy(old)
        new["rules"].append({"id": "x", "text": "t"})
        new["classes"]["Persona"]["rules"][0]["text"] = "changed"
        new["classes"]["Nuova"] = {"attributes": {"n": "EString"}, "rules": [{"id": "r", "text": "t"}]}
        d = E.diff(old, new)
        for line in ("+ rule x", "~ Persona: rule indirizzo_attivo changed", "+ class Nuova", "  + Nuova: rule r"):
            self.assertIn(line, d)
        del new["classes"]["Persona"]["rules"]
        self.assertIn("- Persona: rule indirizzo_attivo", E.diff(old, new))

    def test_markdown(self):
        meta = E.load(FIXTURE)
        md = E.to_markdown(meta)
        for s in ["# Dominio anagrafica", "## Diagramma", "```mermaid", "Soggetto <|-- Persona", "## Regole generali",
                  "- `email_unica`: Un account per persona con email unica nel sistema", "## Soggetto", "*Astratta.*",
                  "## Persona", "Una persona fisica. Estende Soggetto.", "### Attributi",
                  "| codiceFiscale | EString | 1 | identificativo |  |", "| nome | EString | 1 | max 120 caratteri |  |",
                  "| ruolo | Ruolo | 0..1 | default STAFF |  |", "### Riferimenti",
                  "| indirizzi | Indirizzo | 0..* | contenimento, opposto `persona` |  |",
                  "### Regole", "- `indirizzo_attivo`: Una persona attiva ha almeno un indirizzo",
                  "## Enum", "### Ruolo", "| OSPITE | Ospite esterno |"]:
            self.assertIn(s, md)
        self.assertNotIn("### Regole", md.split("## Account")[1].split("## Indirizzo")[0])   # no empty blocks
        self.assertEqual(md, E.to_markdown(meta))
        en = E.to_markdown(meta, "en")
        for s in ["# Domain anagrafica", "## General rules", "### Attributes", "*Abstract.*", "Extends Soggetto.",
                  "| OSPITE | External guest |"]:
            self.assertIn(s, en)
        m2 = copy.deepcopy(meta)
        m2["classes"]["Persona"]["label"] = {"it": "Persona fisica", "en": "Person"}
        m2["classes"]["Persona"]["attributes"]["dataNascita"] = {"type": "Date", "doc": "Data di nascita", "help": "gg/mm/aaaa"}
        self.assertIn("## Persona fisica (`Persona`)", E.to_markdown(m2))
        self.assertIn("## Person (`Persona`)", E.to_markdown(m2, "en"))
        self.assertIn("| dataNascita | Date | 0..1 |  | Data di nascita (gg/mm/aaaa) |", E.to_markdown(m2))
        self.assertIn("| persona | Persona fisica | 1 | opposto `indirizzi` |  |", E.to_markdown(m2))   # label in "Verso"

    def test_markdown_sections_and_changes(self):
        meta = E.load(FIXTURE)
        doc = E.markdown_document(meta)
        secs = E.markdown_sections(E.markdown_split(doc)[1])
        for k in ["(intro)", "Diagramma", "Regole generali", "Persona", "Persona › Attributi", "Persona › Regole", "Enum › Ruolo"]:
            self.assertIn(k, secs)
        rule = "- `indirizzo_attivo`: Una persona attiva ha almeno un indirizzo\n"
        edited = doc.replace(rule, rule + "- Una persona non può avere due account\n")
        ch = E.markdown_changes(doc, edited)
        self.assertEqual([c["name"] for c in ch], ["Persona › Regole"])
        self.assertIn("+- Una persona non può avere due account", ch[0]["diff"])
        # a formatter is not a hand edit: trailing spaces, padded tables, separator rows, re-wrapped paragraphs
        pretty = "\n".join(line + "   " if line.startswith("|") else line for line in doc.splitlines())
        pretty = pretty.replace("|---|---|---|---|---|", "| --- | --- | --- | --- | --- |")
        pretty = pretty.replace("| codiceFiscale | EString | 1 |", "| codiceFiscale   | EString | 1   |")
        pretty = pretty.replace("Anagrafica di prova con tutti i costrutti", "Anagrafica di prova\ncon tutti i costrutti")
        self.assertEqual(E.markdown_changes(doc, pretty), [])
        self.assertEqual(E.markdown_checksum(E.markdown_split(pretty)[1]), E.markdown_split(doc)[0])
        self.assertEqual([c["name"] for c in E.markdown_changes(doc, doc + "\n## Note\n\nqualcosa\n")], ["Note (new)"])
        self.assertEqual([c["name"] for c in E.markdown_changes(doc, doc + "\n---\n")], ["Enum › Ruolo"])   # a rule is content
        self.assertNotIn("InTilde", E.markdown_sections("## A\n\n~~~\n## InTilde\n~~~\n"))
        self.assertEqual(E.validate({**meta, "classes": {**meta["classes"], "Allegato": {**meta["classes"]["Allegato"], "rules": None}}}).ok, True)

    def test_storage_mapping(self):
        st = E.storage(E.load(FIXTURE))
        ents = st["entities"]
        self.assertNotIn("Soggetto", ents)                                  # abstract: no table
        self.assertEqual(ents["Persona"]["table"], "persone")                # language: it
        self.assertEqual(ents["Indirizzo"]["table"], "indirizzi")
        self.assertEqual(ents["Account"]["table"], "account")
        p = ents["Persona"]["fields"]
        self.assertIn("nome", p)                                            # inherited from Soggetto
        self.assertTrue(p["codice_fiscale"]["unique"])                      # id attribute
        self.assertEqual(ents["Persona"]["display"], "codice_fiscale")
        self.assertTrue(p["account"]["required"] and p["account"]["unique"])  # one-to-one on the mandatory side
        self.assertNotIn("persona", ents["Account"]["fields"])              # the other end has no column
        self.assertTrue(p["gruppi"]["many"])                                # many-to-many owned by Persona
        self.assertNotIn("membri", ents["Gruppo"]["fields"])
        ind = ents["Indirizzo"]["fields"]["persona"]                         # containment with opposite
        self.assertEqual((ind["required"], ind["on_delete"]), (True, "cascade"))
        alle = ents["Allegato"]["fields"]["gruppo"]                          # containment without opposite
        self.assertEqual((alle["to"], alle["on_delete"]), ("Gruppo", "cascade"))
        self.assertEqual(p["utente"]["on_delete"], "set_null")              # optional reference
        self.assertEqual(p["ruolo"]["default"], "staff")                    # literal STAFF → staff
        self.assertEqual(st["enums"]["Ruolo"], ["admin", "staff", "ospite"])

    def test_english_tables(self):
        st = E.storage({"package": "t", "classes": {"BookingItem": {"attributes": {"label": "EString"}}}})
        self.assertEqual(st["entities"]["BookingItem"]["table"], "booking_items")

    def test_errors_are_reported(self):
        cases = {
            "polymorphic": ({"classes": {"A": {"abstract": True}, "B": {"supertypes": ["A"]}, "C": {"supertypes": ["A"]},
                                         "D": {"references": {"a": "A"}}}}, "polymorphic"),
            "unknown type": ({"classes": {"A": {"attributes": {"x": "Strin"}}}}, "unknown data type"),
            "class as attribute": ({"classes": {"A": {}, "B": {"attributes": {"a": "A"}}}}, "declare it under references"),
            "opposite": ({"classes": {"A": {"references": {"b": {"type": "B", "opposite": "a"}}},
                                      "B": {"references": {"a": {"type": "A", "opposite": "x"}}}}}, "must declare opposite"),
            "behaviour in metamodel": ({"classes": {"A": {"workflow": {}}}}, "unknown keys: workflow"),
            "top-level behaviour": ({"classes": {"A": {}}, "roles": []}, "structure only"),
            "reserved": ({"classes": {"A": {"attributes": {"createdAt": "EDate"}}}}, "standard column"),
            "user declared": ({"classes": {"User": {}}}, "built in"),
            "cycle": ({"classes": {"A": {"supertypes": ["B"]}, "B": {"supertypes": ["A"]}}}, "cycle"),
            "column clash": ({"classes": {"A": {"attributes": {"b": "EString"}, "references": {"b": "B"}},
                                          "B": {}}}, "declared twice"),
        }
        for name, (raw, needle) in cases.items():
            self.assertIn(needle, E.validate({"package": "t", **raw}).render(), name)

    def test_common_column_names_are_allowed(self):
        raw = {"package": "t", "classes": {"Item": {"attributes": {"type": "EString", "state": "EString", "data": "JSON"}}}}
        self.assertTrue(E.validate(raw).ok, E.validate(raw).render())

    def test_diff(self):
        old = E.load(FIXTURE)
        new = copy.deepcopy(old)
        new["classes"]["Persona"]["attributes"]["telefono"] = "EString"
        new["classes"]["Persona"]["attributes"]["cf"] = {**new["classes"]["Persona"]["attributes"].pop("codiceFiscale"),
                                                        "renamed_from": "codiceFiscale"}
        del new["classes"]["Allegato"]
        changes = E.diff(old, new)
        self.assertIn("+ Persona.telefono: EString", changes)
        self.assertIn("~ Persona.codiceFiscale renamed to cf", changes)
        self.assertIn("- class Allegato", changes)

    def test_views(self):
        meta = E.load(FIXTURE)
        self.assertIn("val Indirizzo[*]#persona indirizzi;", E.to_emfatic(meta))
        self.assertIn("Soggetto <|-- Persona", E.to_mermaid(meta))

    def test_legacy_ecore_annotations_are_read(self):
        text = E.export_ecore(E.load(FIXTURE)).replace('source="modeler"', 'source="appforge"')
        self.assertEqual(E.expand(E.import_ecore(text))["enums"], E.expand(E.load(FIXTURE))["enums"])


def _evolved(meta):
    """The fixture after a typical change: a column, a rename, a join table, a literal, a new class, a drop."""
    new = copy.deepcopy(meta)
    p = new["classes"]["Persona"]
    p["attributes"]["telefono"] = {"type": "EString", "max_length": 30}
    p["attributes"]["nascita"] = {"type": "Date", "renamed_from": "dataNascita"}
    del p["attributes"]["dataNascita"]
    p["attributes"]["matricola"] = {"type": "EString", "lower": 1}
    new["classes"]["Account"]["references"] = {
        "persona": {"type": "Persona", "opposite": "account"},
        "etichette": {"type": "Etichetta", "upper": -1}}
    new["classes"]["Etichetta"] = {"attributes": {"nome": {"type": "EString", "lower": 1}}}
    new["enums"]["Ruolo"].append("REVISORE")
    del new["classes"]["Gruppo"]["attributes"]["nome"]
    return new


def _tariffs(unique=("voce", "motivo", "posizione")):
    """A lookup on three dimensions: the row without posizione is the default of voce x motivo."""
    meta = {"package": "tariffe", "language": "it", "classes": {
        "Voce": {"attributes": {"nome": {"type": "EString", "lower": 1}}},
        "Posizione": {"attributes": {"nome": {"type": "EString", "lower": 1}}},
        "Tariffa": {"attributes": {"motivo": {"type": "Motivo", "lower": 1}, "importo": "Money"},
                    "references": {"voce": {"type": "Voce", "lower": 1}, "posizione": "Posizione"}}},
        "enums": {"Motivo": ["NASCITA", "MATRIMONIO"]}}
    if unique:
        meta["classes"]["Tariffa"]["unique"] = [list(unique)]
    return meta


class UniqueTogetherTests(unittest.TestCase):
    """Class-level unique: combinations of features that must be unique (lookups on several dimensions)."""

    def test_notation_storage_and_round_trips(self):
        meta = _tariffs()
        self.assertTrue(E.validate(meta).ok, E.validate(meta).render())
        self.assertEqual(E.storage(meta)["entities"]["Tariffa"]["unique"], [["voce", "motivo", "posizione"]])
        self.assertEqual(E.expand(E.loads(E.dumps(meta))), E.expand(meta))
        self.assertEqual(E.expand(E.import_ecore(E.export_ecore(meta)))["classes"], E.expand(meta)["classes"])
        one = _tariffs(None)
        one["classes"]["Tariffa"]["unique"] = ["voce", "motivo"]                 # one group, written flat
        self.assertEqual(E.expand(one)["classes"]["Tariffa"]["unique"], [["voce", "motivo"]])

    def test_inherited_by_the_subclasses(self):
        meta = _tariffs(None)
        meta["classes"]["Base"] = {"abstract": True, "attributes": {"codice": "EString", "anno": "EInt"},
                                   "unique": [["codice", "anno"]]}
        meta["classes"]["Voce"]["supertypes"] = ["Base"]
        self.assertTrue(E.validate(meta).ok, E.validate(meta).render())
        self.assertEqual(E.storage(meta)["entities"]["Voce"]["unique"], [["codice", "anno"]])

    def test_errors(self):
        def errors(group):
            meta = _tariffs(None)
            meta["classes"]["Tariffa"]["unique"] = group
            return E.validate(meta).render()
        self.assertIn("two or more features", errors([["voce"]]))
        self.assertIn("'colore' is not a feature of Tariffa", errors([["voce", "colore"]]))
        meta = _tariffs(None)
        meta["classes"]["Voce"]["references"] = {"tariffe": {"type": "Tariffa", "upper": -1}}
        meta["classes"]["Voce"]["unique"] = [["nome", "tariffe"]]
        self.assertIn("'tariffe' is multi-valued", E.validate(meta).render())
        meta = _tariffs(None)                         # the foreign key of a one-to-one is in the other table
        meta["classes"]["Posizione"]["references"] = {"tariffa": {"type": "Tariffa", "opposite": "posizione"}}
        meta["classes"]["Tariffa"]["references"]["posizione"] = {"type": "Posizione", "opposite": "tariffa"}
        meta["classes"]["Tariffa"]["unique"] = [["motivo", "posizione"]]
        self.assertIn("posizione: not a column of Tariffa", E.validate(meta).render())

    def test_migration_and_diff(self):
        sql, _ = G.migration({"package": "t", "classes": {}}, _tariffs())
        add = "alter table public.tariffe add constraint tariffe_voce_motivo_posizione_key unique nulls not distinct (voce, motivo, posizione);"
        self.assertIn(add, sql)
        self.assertLess(sql.index("add column posizione"), sql.index(add))     # after the reference columns
        sql, notes = G.migration(_tariffs(None), _tariffs())
        self.assertIn(add, sql)
        self.assertTrue(any("duplicates" in n for n in notes))
        sql, _ = G.migration(_tariffs(), _tariffs(None))
        self.assertIn("alter table public.tariffe drop constraint if exists tariffe_voce_motivo_posizione_key;", sql)
        self.assertEqual(G.migration(_tariffs(), _tariffs())[0], "")
        self.assertIn("+ Tariffa: unique (voce, motivo, posizione)", E.diff(_tariffs(None), _tariffs()))

    def test_drift_and_reverse_from_a_catalog(self):
        cols = [("voci", "nome", "text", False), ("posizioni", "nome", "text", False),
                ("tariffe", "motivo", "text", False), ("tariffe", "importo", "numeric", True),
                ("tariffe", "voce", "uuid", False), ("tariffe", "posizione", "uuid", True)]
        cat = {"tables": ["posizioni", "tariffe", "voci"], "enums": [], "unique_indexes": [],
               "columns": [{"table": t, "name": "id", "udt": "uuid", "type": "uuid", "nullable": False,
                            "default": "gen_random_uuid()", "maxlen": None} for t in ("voci", "posizioni", "tariffe")]
               + [{"table": t, "name": n, "udt": u, "type": u, "nullable": nl, "default": None, "maxlen": None}
                  for t, n, u, nl in cols],
               "constraints": [
                   {"table": "tariffe", "name": "f1", "type": "f", "columns": ["voce"], "ftable": "voci",
                    "fschema": "public", "on_delete": "r", "def": ""},
                   {"table": "tariffe", "name": "f2", "type": "f", "columns": ["posizione"], "ftable": "posizioni",
                    "fschema": "public", "on_delete": "n", "def": ""},
                   {"table": "tariffe", "name": "c1", "type": "c", "columns": ["motivo"], "ftable": None, "fschema": None,
                    "on_delete": None, "def": "CHECK ((motivo = ANY (ARRAY['nascita'::text, 'matrimonio'::text])))"}]}
        meta = _tariffs()
        meta["classes"]["Tariffa"]["attributes"]["motivo"] = {"type": "Motivo", "lower": 1}
        self.assertIn("MISSING UNIQUE tariffe (voce, motivo, posizione)", D.drift(meta, cat))
        cat["unique_indexes"] = [{"table": "tariffe", "name": "tariffe_combo", "columns": ["voce", "motivo", "posizione"],
                                  "expressions": False,
                                  "def": "CREATE UNIQUE INDEX tariffe_combo ON public.tariffe USING btree (voce, motivo, posizione)"}]
        self.assertTrue(any(x.startswith("UNIQUE tariffe (voce, motivo, posizione): nulls are distinct")
                            for x in D.drift(meta, cat)))
        rev, notes = D.reverse(cat, package="tariffe")
        tariffa = next(c for c in E.expand(rev)["classes"].values() if c.get("table") == "tariffe")
        self.assertEqual(tariffa["unique"], [["voce", "motivo", "posizione"]])
        self.assertTrue(any("treats empty values as distinct" in n for n in notes))
        cat["unique_indexes"][0]["def"] = cat["unique_indexes"][0]["def"] + " NULLS NOT DISTINCT"
        self.assertFalse(any("unique" in x.lower() for x in D.drift(meta, cat)), D.drift(meta, cat))


class PatchTextTests(unittest.TestCase):
    """`patch_text` rewrites only the lines of what changed in a metamodel written by hand."""

    def setUp(self):
        self.text = FIXTURE.read_text()
        self.meta = E.load(FIXTURE)

    def changed(self, new):
        out = E.patch_text(self.text, new)
        self.assertIsNotNone(out)
        self.assertEqual(E.expand(E.loads(out)), E.expand(new))
        return [x for x in difflib.unified_diff(self.text.splitlines(), out.splitlines(), n=0)
                if x[:1] in "+-" and not x.startswith(("+++", "---"))]

    def test_rules_rewrite_only_their_block(self):
        new = copy.deepcopy(self.meta)
        new["classes"]["Persona"]["rules"][0]["text"] = "Una persona attiva ha un indirizzo"
        lines = self.changed(new)
        self.assertTrue(any("Una persona attiva ha un indirizzo" in x for x in lines))
        self.assertFalse(any("email_unica" in x or "Account:" in x or "Gruppo:" in x for x in lines), lines)
        new = copy.deepcopy(self.meta)
        new["rules"][0]["text"] = "Email unica"
        lines = self.changed(new)
        self.assertEqual(len(lines), 2, lines)                                              # one item of the block
        self.assertTrue(all("email_unica" in x for x in lines))
        new = copy.deepcopy(self.meta)
        new["rules"] = []
        lines = self.changed(new)
        self.assertEqual(sorted(x[:1] for x in lines), ["-", "-"])                           # block removed
        text = self.text.replace("\nrules:\n  - {id: email_unica, text: Un account per persona con email unica nel sistema}\n", "")
        self.assertNotIn("email_unica", text)
        new = copy.deepcopy(E.loads(text))
        new["rules"] = [{"id": "x", "text": "t"}]
        out = E.patch_text(text, new)
        self.assertIsNotNone(out)
        self.assertEqual(E.expand(E.loads(out)), E.expand(new))                              # block added at the end
        self.assertTrue(out.rstrip("\n").endswith("rules:\n  - {id: x, text: t}"), out[-80:])
        with_diagram = text + "\ndiagram:\n  Persona: {x: 1, y: 2}\n"
        new = copy.deepcopy(E.loads(with_diagram))
        new["rules"] = [{"id": "x", "text": "t"}]
        out = E.patch_text(with_diagram, new)
        self.assertEqual(E.expand(E.loads(out)), E.expand(new))
        self.assertIn("\n\nrules:\n  - {id: x, text: t}\n\ndiagram:\n", out)                   # before the diagram, one blank line each side

    def test_features_classes_enums_and_diagram(self):
        new = E.expand(self.meta)
        new["classes"]["Persona"]["attributes"]["codice"] = {"type": "EString", "lower": 0, "upper": 1}
        self.assertEqual(self.changed(new), ["+      codice: EString"])
        new = E.expand(self.meta)
        del new["classes"]["Persona"]["references"]["utente"]
        self.assertEqual(self.changed(new), ["-      utente: User"])
        new = E.expand(self.meta)
        del new["classes"]["Allegato"]
        del new["classes"]["Gruppo"]["references"]["allegati"]
        self.assertEqual(self.changed(new), ["-      allegati: {type: Allegato, upper: \"*\", containment: true}",
                                             "-  Allegato:", "-    attributes: {file: URL}"])
        new = E.expand(self.meta)
        new["classes"]["Etichetta"] = {"attributes": {"nome": {"type": "EString", "lower": 0, "upper": 1}}}
        self.assertEqual(self.changed(new), ["+  Etichetta: {attributes: {nome: EString}}"])
        new = E.expand(self.meta)
        new["enums"]["Ruolo"]["literals"].append({"name": "REVISORE"})
        self.assertTrue(all("Ruolo" in x or "REVISORE" in x or x.strip("+-").strip().startswith(("-", "literals"))
                            for x in self.changed(new)))
        new = E.expand(self.meta)
        new["diagram"] = {"Persona": {"x": 0, "y": 0}}
        self.assertIsNone(E.patch_text(self.text, new))         # no diagram section yet: whole rewrite

    def test_inline_attributes_rewrite_only_their_class(self):
        new = E.expand(self.meta)
        new["classes"]["Indirizzo"]["attributes"]["cap"] = {"type": "EString", "lower": 0, "upper": 1}
        lines = self.changed(new)
        self.assertTrue(lines and all("via" in x or "cap" in x or "Indirizzo" in x or "persona" in x or "attributes" in x
                                      or "references" in x for x in lines), lines)

    def test_header_change_is_left_to_a_full_rewrite(self):
        new = E.expand(self.meta)
        new["doc"] = "altro"
        self.assertIsNone(E.patch_text(self.text, new))


class MigrationTests(unittest.TestCase):
    def test_no_change_no_migration(self):
        meta = E.load(FIXTURE)
        self.assertEqual(G.migration(meta, meta)[0], "")

    def test_whole_schema_from_empty(self):
        sql, _ = G.migration({"package": "t", "classes": {}}, E.load(FIXTURE))
        self.assertIn("create table public.persone (", sql)
        self.assertIn("nome varchar(120) not null", sql)
        self.assertIn("ruolo text default 'staff' check (ruolo in ('admin', 'staff', 'ospite'))", sql)
        self.assertIn("add column account uuid not null unique references public.account (id) on delete restrict", sql)
        self.assertIn("add column utente uuid references public.profiles (id) on delete set null", sql)
        self.assertIn("add column gruppo uuid not null references public.gruppi (id) on delete cascade", sql)
        self.assertIn("create table public.persone_gruppi (", sql)
        self.assertIn("persona_id uuid not null references public.persone (id) on delete cascade", sql)
        self.assertIn("TODO(modeler): row level security is on for persone", sql)

    def test_evolution(self):
        meta = E.load(FIXTURE)
        sql, notes = G.migration(meta, _evolved(meta))
        self.assertIn("alter table public.persone add column telefono varchar(30);", sql)
        self.assertIn("alter table public.persone rename column data_nascita to nascita;", sql)
        self.assertNotIn("drop column data_nascita", sql)                       # a rename, not a drop
        self.assertIn("alter table public.persone add column matricola text;", sql)   # required: nullable first
        self.assertIn("-- alter table public.persone alter column matricola set not null;", sql)
        self.assertIn("create table public.etichette (", sql)
        self.assertIn("create table public.account_etichette (", sql)
        self.assertIn("alter type public.ruolo add value if not exists 'revisore';", sql)
        self.assertIn("check (ruolo in ('admin', 'staff', 'ospite', 'revisore'))", sql)
        self.assertIn("-- alter table public.gruppi drop column nome;", sql)      # destructive: commented
        self.assertTrue(any("backfill" in n for n in notes))

    def test_type_change_is_left_to_review(self):
        meta = E.load(FIXTURE)
        new = copy.deepcopy(meta)
        new["classes"]["Indirizzo"]["attributes"]["via"] = "EInt"
        sql, _ = G.migration(meta, new)
        self.assertIn("-- alter table public.indirizzi alter column via type integer using via::integer;", sql)

    def test_cli_from_git_head(self):
        with tempfile.TemporaryDirectory() as d:
            app = Path(d)
            git = lambda *a: subprocess.run(["git", *a], cwd=app, check=True, capture_output=True)  # noqa: E731
            git("init", "-q", "-b", "main")
            git("config", "user.email", "t@e.org")
            git("config", "user.name", "T")
            meta = E.load(FIXTURE)
            E.dump(meta, app / "domain.ecore.yaml")
            git("add", "-A")
            git("commit", "-q", "-m", "init")
            ns = argparse.Namespace(path=str(app), from_="HEAD", name=None, write=True)
            self.assertEqual(cli.cmd_migrate(ns), 0)                            # unchanged: nothing written
            self.assertFalse((app / "supabase").exists())
            E.dump(_evolved(meta), app / "domain.ecore.yaml")
            self.assertEqual(cli.cmd_migrate(argparse.Namespace(path=str(app), from_="HEAD", name="Telefono e tag!",
                                                                write=True)), 0)
            files = list((app / "supabase" / "migrations").glob("*_telefono_e_tag.sql"))
            self.assertEqual(len(files), 1)
            self.assertIn("rename column data_nascita to nascita", files[0].read_text())


class AppTests(unittest.TestCase):
    """The modeler as part of an application."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Path(self.tmp.name) / "app"
        (self.app / "supabase").mkdir(parents=True)
        (self.app / "package.json").write_text(json.dumps({"name": "app", "scripts": {"dev": "next dev"}}))
        (self.app / "supabase" / "config.toml").write_text('[api]\nport = 55121\n\n[db]\nport = 55122\n')
        (self.app / "domain.ecore.yaml").write_text(FIXTURE.read_text())

    def tearDown(self):
        self.tmp.cleanup()

    def test_install_makes_the_modeler_part_of_the_app(self):
        written = cli.install(self.app)
        for rel in ("public/modeler/metamodel-editor.js", "src/components/modeler/metamodel-modeler.tsx",
                    "src/components/modeler/behavior-view.tsx", "src/components/modeler/workflow-view.tsx",
                    "src/lib/modeler/metamodel-actions.ts", "src/lib/modeler/access.ts", "docs/DOMAIN.md",
                    "src/lib/modeler/metamodel.json", "tools/modeler/modeler.py",
                    "tools/modeler/metamodel/ecore.py", "tools/modeler/vendor/yaml/__init__.py"):
            self.assertTrue((self.app / rel).exists(), rel)
        self.assertTrue(any(w.endswith("_model_change_requests.sql") for w in written))
        self.assertEqual(cli.installed_version(self.app), __version__)
        scripts = json.loads((self.app / "package.json").read_text())["scripts"]
        self.assertEqual(scripts["dev"], "next dev")
        self.assertEqual(scripts["model:drift"], cli.NPM_SCRIPTS["model:drift"])
        self.assertEqual(scripts["model:migrate"], cli.NPM_SCRIPTS["model:migrate"])
        self.assertEqual(scripts["model:docs"], cli.NPM_SCRIPTS["model:docs"])
        self.assertIn("## Persona", (self.app / "docs/DOMAIN.md").read_text())
        self.assertEqual(cli.docs_status(self.app)["state"], "aligned")
        doc = json.loads((self.app / "src/lib/modeler/metamodel.json").read_text())
        self.assertIn("Persona", doc["classes"])
        self.assertNotIn("appforge", (self.app / "src/lib/modeler/metamodel-actions.ts").read_text())
        editor = (self.app / "public/modeler/metamodel-editor.js").read_text()
        self.assertIn(f'const VERSION = "{__version__}";', editor)                # shown in the toolbar
        self.assertNotIn(cli.VERSION_PLACEHOLDER, editor)
        self.assertIn('customElements.define("workflow-view"', editor)      # the record pages draw the workflow with it

    def test_install_tells_when_the_page_does_not_show_the_behaviour(self):
        # no behavior.yaml: nothing to say
        self.assertIsNone(cli.behavior_page_hint(self.app))
        fixtures = Path(__file__).resolve().parent / "fixtures"
        (self.app / "domain.ecore.yaml").write_text((fixtures / "invitations.ecore.yaml").read_text())
        (self.app / "behavior.yaml").write_text((fixtures / "invitations.behavior.yaml").read_text())
        page = self.app / "src/app/(admin)/admin/model/page.tsx"
        page.parent.mkdir(parents=True)
        page.write_text((cli.KIT_DIR / "next" / "page.tsx").read_text())      # the template, behaviour still commented out
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.cmd_install(argparse.Namespace(app=str(self.app), no_migration=True)), 0)
        self.assertIn("behavior.yaml found", out.getvalue())
        self.assertIn("src/app/(admin)/admin/model/page.tsx", out.getvalue())
        self.assertIn("behavior={behavior}", out.getvalue())
        self.assertTrue((self.app / "src/lib/modeler/behavior.json").exists())   # sync wrote what the page should import
        # the page passes it: nothing more to do; the wrapper itself never counts as a page
        page.write_text(page.read_text().replace("// import behavior", "import behavior")
                        .replace("canEdit lang", "behavior={behavior} canEdit lang"))
        self.assertIsNone(cli.behavior_page_hint(self.app))
        self.assertEqual([p.name for p in cli.modeler_pages(self.app)], ["page.tsx"])
        # no page yet (first installation): the hint points to the skill
        page.unlink()
        self.assertIn("see the install skill", cli.behavior_page_hint(self.app))

    def test_install_stops_on_a_docs_domain_md_with_other_case(self):
        other = self.app / "docs" / "domain.md"                          # appforge's document, not hand notes
        other.parent.mkdir(parents=True)
        other.write_text("# Behaviour\n\nroles and workflow\n")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.cmd_install(argparse.Namespace(app=str(self.app), no_migration=True)), 0)
        self.assertEqual(sorted(os.listdir(self.app / "docs")), ["domain.md"])   # no DOMAIN.md, nothing overwritten
        self.assertEqual(other.read_text(), "# Behaviour\n\nroles and workflow\n")
        self.assertFalse((self.app / ".modeler" / "DOMAIN.generated.md").exists())
        self.assertIn("docs/domain.md differs from docs/DOMAIN.md only by letter case", out.getvalue())
        self.assertIn("docs/behavior.md", out.getvalue())
        st = cli.docs_status(self.app)
        self.assertEqual((st["state"], st["other"]), ("clash", "docs/domain.md"))
        ns = lambda **kw: argparse.Namespace(path=str(self.app), **kw)   # noqa: E731
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            self.assertEqual(cli.cmd_sync(ns(force=True)), 1)                      # even --force keeps it
        self.assertIn("letter case", err.getvalue())
        self.assertEqual(sorted(os.listdir(self.app / "docs")), ["domain.md"])
        other.rename(self.app / "docs" / "behavior.md")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.cmd_sync(ns(force=False)), 0)
        self.assertEqual(sorted(os.listdir(self.app / "docs")), ["DOMAIN.md", "behavior.md"])
        self.assertEqual(cli.docs_status(self.app)["state"], "aligned")

    def test_sync_keeps_hand_edits_in_domain_md(self):
        cli.install(self.app)
        md = self.app / "docs/DOMAIN.md"
        ns = lambda **kw: argparse.Namespace(path=str(self.app), **kw)   # noqa: E731
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.cmd_sync(ns(force=False)), 0)
        before = md.read_text()
        md.write_text(before.replace("### Regole\n\n", "### Regole\n\n- Una persona non può avere due account\n", 1))
        st = cli.docs_status(self.app)
        self.assertEqual(st["state"], "edited")
        self.assertEqual([x["name"] for x in st["sections"]], ["Persona › Regole"])
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            self.assertEqual(cli.cmd_sync(ns(force=False)), 1)                       # kept, with the sections
        self.assertIn("Persona › Regole", err.getvalue())
        self.assertIn("due account", md.read_text())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.cmd_docs(ns()), 1)
        self.assertIn("+- Una persona non può avere due account", out.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.cmd_sync(ns(force=True)), 0)
        self.assertEqual(md.read_text(), before)
        self.assertTrue(list((self.app / ".modeler" / "backups").glob("DOMAIN.md.*")))
        y = self.app / "domain.ecore.yaml"                                           # the metamodel changes: stale
        y.write_text(y.read_text().replace("      dataNascita: Date\n", "      dataNascita: Date\n      telefono: EString\n"))
        self.assertEqual(cli.docs_status(self.app)["state"], "stale")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.cmd_sync(ns(force=False)), 0)
        self.assertEqual(cli.docs_status(self.app)["state"], "aligned")
        self.assertIn("| telefono |", md.read_text())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.cmd_show(argparse.Namespace(path=str(self.app), format="markdown"))
        self.assertTrue(out.getvalue().startswith("# Dominio anagrafica"))             # no marker line
        # a hand note and a metamodel change together: only the note is reported, the file is kept
        current = md.read_text()
        md.write_text(current.replace("### Regole\n\n", "### Regole\n\n- Nota a mano\n", 1))
        y.write_text(y.read_text().replace("      telefono: EString\n", "      telefono: EString\n      fax: EString\n"))
        st = cli.docs_status(self.app)
        self.assertEqual((st["state"], [x["name"] for x in st["sections"]], st["metamodel_changed"]),
                         ("edited", ["Persona › Regole"], True))
        self.assertIn("metamodel changed too", cli.docs_report(st))
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.cmd_sync(ns(force=False)), 1)
        self.assertIn("Nota a mano", md.read_text())
        # the marker deleted by hand: not an edit
        md.write_text(current.split("\n", 1)[1])
        self.assertEqual(cli.docs_status(self.app)["state"], "stale")                 # the metamodel has fax now
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.cmd_sync(ns(force=False)), 0)
        md.write_text("\ufeff" + md.read_text().split("\n", 1)[1])                    # BOM and no marker
        self.assertEqual(cli.docs_status(self.app)["state"], "aligned")

    def test_apply_keeps_an_edited_domain_md(self):
        cli.install(self.app)
        md = self.app / "docs/DOMAIN.md"
        md.write_text(md.read_text() + "\n## Note\n\nDa tradurre\n")
        doc = json.loads((self.app / "src/lib/modeler/metamodel.json").read_text())
        doc["classes"]["Persona"]["attributes"]["telefono"] = {"type": "EString", "lower": 0, "upper": 1}
        (self.app / "p.json").write_text(json.dumps({"metamodel": doc}))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ns = argparse.Namespace(path=str(self.app), proposal=str(self.app / "p.json"), write=True, rewrite=False)
            self.assertEqual(cli.cmd_apply(ns), 0)
        self.assertIn("Note (new)", out.getvalue())
        self.assertIn("Da tradurre", md.read_text())
        self.assertIn("telefono", (self.app / "src/lib/modeler/metamodel.json").read_text())

    def test_install_ignores_python_bytecode(self):
        (self.app / ".gitignore").write_text("node_modules/\n.env*")
        cli.install(self.app)
        text = (self.app / ".gitignore").read_text()
        self.assertTrue(text.startswith("node_modules/\n.env*\n"))
        self.assertEqual(text.count("__pycache__/"), 1)
        cli.install(self.app)                                   # idempotent
        self.assertEqual((self.app / ".gitignore").read_text(), text)
        (self.app / ".gitignore").unlink()
        cli.install(self.app)                                   # created when missing
        self.assertIn("__pycache__/", (self.app / ".gitignore").read_text())

    def test_reinstall_upgrades_owned_files_and_keeps_adapted_ones(self):
        cli.install(self.app)
        (self.app / "src/lib/modeler/access.ts").write_text("// adapted to the app\n")
        (self.app / "public/modeler/metamodel-editor.js").write_text("// old\n")
        (self.app / "tools/modeler/VERSION").write_text("0.0.1\n")
        written = cli.install(self.app)
        self.assertEqual((self.app / "src/lib/modeler/access.ts").read_text(), "// adapted to the app\n")
        self.assertIn("customElements", (self.app / "public/modeler/metamodel-editor.js").read_text())
        self.assertEqual(cli.installed_version(self.app), __version__)
        self.assertFalse(any(w.endswith("_model_change_requests.sql") for w in written))   # migration once

    def test_vendored_cli_runs_without_the_plugin(self):
        cli.install(self.app)
        run = lambda *args: subprocess.run([sys.executable, "tools/modeler/modeler.py", *args],  # noqa: E731
                                           cwd=self.app, capture_output=True, text=True)
        out = run("validate")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("Metamodel OK", out.stdout)
        self.assertIn("persone (Persona)", run("show", "--format", "storage").stdout)
        out = run("install")
        self.assertNotEqual(out.returncode, 0)                               # the kit lives only in the plugin

    def test_local_dsn_from_supabase_config(self):
        self.assertEqual(cli.local_dsn(self.app), "postgresql://postgres:postgres@127.0.0.1:55122/postgres")

    def test_remote_dsn_from_linked_project(self):
        env = {k: v for k, v in os.environ.items() if k != "MODELER_PROD_DB"}
        with unittest.mock.patch.dict(os.environ, env, clear=True):
            self.assertIsNone(cli.remote_dsn(self.app))                      # never the local database
            temp = self.app / "supabase" / ".temp"
            temp.mkdir(parents=True)
            (temp / "project-ref").write_text("abcref\n")
            self.assertEqual(cli.remote_dsn(self.app), "postgresql://postgres@db.abcref.supabase.co:5432/postgres")
            pooler = "postgresql://postgres.abcref@aws-0-eu-central-1.pooler.supabase.com:6543/postgres"
            (temp / "pooler-url").write_text(pooler + "\n")
            self.assertEqual(cli.remote_dsn(self.app), pooler)
            os.environ["MODELER_PROD_DB"] = "postgresql://u:p@host/db"
            self.assertEqual(cli.remote_dsn(self.app), "postgresql://u:p@host/db")

    def test_dsn_target_hides_the_password(self):
        self.assertEqual(cli._dsn_target("postgresql://u:secret@h:5432/db"), "u@h:5432/db")
        self.assertTrue(cli._has_password("postgresql://u:secret@h/db"))
        self.assertFalse(cli._has_password("postgresql://postgres.ref@h:6543/postgres"))

    def test_pull_without_a_password_stops_before_psql(self):
        dsn = "postgresql://postgres.abcref@aws-0-eu-central-1.pooler.supabase.com:5432/postgres"
        self.assertEqual(cli._pgpass_line(dsn),
                         "aws-0-eu-central-1.pooler.supabase.com:5432:postgres:postgres.abcref:<password>")
        env = {k: v for k, v in os.environ.items() if k not in ("PGPASSWORD", "SUPABASE_DB_PASSWORD")}
        env["PGPASSFILE"] = str(self.app / "no-pgpass")
        with unittest.mock.patch.dict(os.environ, env, clear=True), \
                unittest.mock.patch.object(cli, "_can_prompt", return_value=False), \
                unittest.mock.patch("subprocess.run") as psql, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(D.DbError) as err:
                cli._prod_query(dsn, "select 1", "pulling from")
            psql.assert_not_called()                                         # nothing sent to production
            self.assertIn("~/.pgpass", str(err.exception))
            self.assertIn(cli._pgpass_line(dsn), str(err.exception))
            os.environ["SUPABASE_DB_PASSWORD"] = "x"                          # a password: psql runs, with -w
            psql.return_value = subprocess.CompletedProcess([], 0, stdout="[]", stderr="")
            self.assertEqual(cli._prod_query(dsn, "select 1", "pulling from"), [])
            self.assertIn("-w", psql.call_args.args[0])
            self.assertEqual(psql.call_args.kwargs["env"]["PGPASSWORD"], "x")
            psql.return_value = subprocess.CompletedProcess([], 2, stdout="", stderr="fe_sendauth: no password supplied")
            with self.assertRaises(D.DbError) as err:                       # e.g. ~/.pgpass without this host
                cli._prod_query(dsn, "select 1", "pulling from")
            self.assertIn(cli._pgpass_line(dsn), str(err.exception))

    def test_pull_without_a_linked_project(self):
        env = {k: v for k, v in os.environ.items() if k != "MODELER_PROD_DB"}
        err = io.StringIO()
        with unittest.mock.patch.dict(os.environ, env, clear=True), contextlib.redirect_stderr(err):
            self.assertEqual(cli.cmd_pull(argparse.Namespace(path=str(self.app), db=None)), 2)
        self.assertIn("supabase link", err.getvalue())

    def _proposal(self, name, edit, **extra):
        doc = json.loads((self.app / "src/lib/modeler/metamodel.json").read_text())
        edit(doc["classes"])
        d = self.app / ".modeler" / "proposals"
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_text(json.dumps({"created_at": name, "metamodel": doc, **extra}))
        return d / name

    def test_apply_archives_the_proposals_it_contains(self):
        cli.install(self.app)
        phone = {"type": "EString", "lower": 0, "upper": 1}
        old = self._proposal("2026-01-01T10-00-00-000Z.json",
                             lambda c: c["Persona"]["attributes"].update(telefono=phone))
        other = self._proposal("2026-01-02T10-00-00-000Z.json",
                               lambda c: c["Persona"]["attributes"].update(fax=phone))
        latest = self._proposal("2026-01-03T10-00-00-000Z.json",
                                lambda c: c["Persona"]["attributes"].update(telefono=phone, email2=phone))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.cmd_apply(argparse.Namespace(path=str(self.app), proposal=None, write=True)), 0)
        applied = self.app / ".modeler" / "proposals" / "applied"
        self.assertTrue((applied / latest.name).exists())
        self.assertTrue((applied / old.name).exists())                       # contained in the latest
        self.assertTrue(other.exists())                                     # fax is not in the latest
        self.assertIn(other.name, out.getvalue().split("Still pending")[1])
        self.assertNotIn("model:done", out.getvalue())                      # saved in development

    def test_a_proposal_with_changes_diff_does_not_print_stays_pending(self):
        cli.install(self.app)
        unique = self._proposal("2026-01-01T10-00-00-000Z.json",
                                lambda c: c["Persona"]["attributes"]["dataNascita"].update(unique=True, label="Nato il"))
        moved = self._proposal("2026-01-02T10-00-00-000Z.json", lambda c: c["Persona"].update(abstract=False))
        self._proposal("2026-01-03T10-00-00-000Z.json", lambda c: c["Persona"]["attributes"].update(
            fax={"type": "EString", "lower": 0, "upper": 1}))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.cmd_apply(argparse.Namespace(path=str(self.app), proposal=None, write=True)), 0)
        self.assertTrue(unique.exists())                                    # unique/label not in the applied one
        self.assertFalse(moved.exists())                                    # no change of its own

    def test_contained(self):
        old, new = {"a": 1, "b": {"c": 1}}, {"a": 2, "b": {"c": 1, "d": 1}}
        self.assertTrue(cli._contained(old, {"a": 2, "b": {"c": 1}}, new))
        self.assertTrue(cli._contained(old, old, new))
        self.assertFalse(cli._contained(old, {"a": 1, "b": {"c": 2}}, new))
        self.assertFalse(cli._contained(old, {"b": {"c": 1}}, new))         # removal of `a` not applied
        self.assertTrue(cli._contained({"a": 1}, {}, {}))

    def test_proposal_id_of_pulled_files(self):
        uid = "0f8e2c4a-1111-4222-8333-944445555666"
        d = self.app / "p"
        d.mkdir()
        (d / "a.json").write_text(json.dumps({"id": uid, "created_at": "x", "metamodel": {}}))
        (d / "2026-01-01T10-00-00-0f8e2c4a.json").write_text(json.dumps({"created_at": "x", "metamodel": {}}))
        (d / "2026-01-01T10-00-00-000Z.json").write_text(json.dumps({"created_at": "x", "metamodel": {}}))
        (d / "closed.json").write_text(json.dumps({"id": uid, "closed": "applied", "created_at": "x", "metamodel": {}}))
        (d / "bad.json").write_text(json.dumps({"id": "x'; drop table t; --", "created_at": "x", "metamodel": {}}))
        self.assertEqual(cli._proposal_id(d / "a.json"), uid)
        self.assertEqual(cli._proposal_id(d / "2026-01-01T10-00-00-0f8e2c4a.json"), "0f8e2c4a")   # older pulls
        self.assertIsNone(cli._proposal_id(d / "2026-01-01T10-00-00-000Z.json"))                 # development
        self.assertIsNone(cli._proposal_id(d / "closed.json"))
        self.assertIsNone(cli._proposal_id(d / "bad.json"))

    def test_done_dry_run_and_nothing_to_close(self):
        out = io.StringIO()
        ns = argparse.Namespace(path=str(self.app), db=None, write=False)
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.cmd_done(ns), 0)
        self.assertIn("nothing to close", out.getvalue())
        applied = self.app / ".modeler" / "proposals" / "applied"
        applied.mkdir(parents=True)
        (applied / "2026-01-01T10-00-00-0f8e2c4a.json").write_text(json.dumps({"created_at": "x", "metamodel": {}}))
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.cmd_done(ns), 0)                            # no database touched
        self.assertIn("applied: 2026-01-01T10-00-00-0f8e2c4a.json", out.getvalue())

    def test_proposal_apply(self):
        cli.install(self.app)
        doc = json.loads((self.app / "src/lib/modeler/metamodel.json").read_text())
        doc["classes"]["Persona"]["attributes"]["telefono"] = {"type": "EString", "lower": 0, "upper": 1}
        prop_dir = self.app / ".modeler" / "proposals"
        prop_dir.mkdir(parents=True)
        (prop_dir / "p1.json").write_text(json.dumps({"note": "telefono", "metamodel": doc}))
        ns = argparse.Namespace(path=str(self.app), proposal=None, write=True)
        self.assertEqual(cli.cmd_apply(ns), 0)
        self.assertIn("telefono", (self.app / "domain.ecore.yaml").read_text())
        self.assertTrue((prop_dir / "applied" / "p1.json").exists())
        self.assertIn("telefono", (self.app / "src/lib/modeler/metamodel.json").read_text())   # synced
        self.assertTrue(list((self.app / ".modeler" / "backups").iterdir()))
        bad = copy.deepcopy(doc)
        bad["classes"]["Persona"]["references"]["account"]["type"] = "Ghost"
        (self.app / "bad.json").write_text(json.dumps({"metamodel": bad}))
        ns = argparse.Namespace(path=str(self.app), proposal=str(self.app / "bad.json"), write=True)
        self.assertEqual(cli.cmd_apply(ns), 1)
        self.assertNotIn("Ghost", (self.app / "domain.ecore.yaml").read_text())


    def test_apply_writes_the_behaviour_of_a_proposal(self):
        fixtures = Path(__file__).resolve().parent / "fixtures"
        (self.app / "domain.ecore.yaml").write_text((fixtures / "invitations.ecore.yaml").read_text())
        (self.app / "behavior.yaml").write_text("# hand comment\n" + (fixtures / "invitations.behavior.yaml").read_text())
        cli.install(self.app)
        meta = json.loads((self.app / "src/lib/modeler/metamodel.json").read_text())
        beh = json.loads((self.app / "src/lib/modeler/behavior.json").read_text())      # what the web modeler holds
        beh["workflows"]["Invitation"]["states"]["paused"] = {"label": {"it": "Sospeso", "en": "Paused"}, "owner": ["office"]}
        beh["workflows"]["Invitation"]["transitions"]["pause"] = {"from": ["in_management"], "to": "paused", "by": ["office"], "label": {"it": "Sospendi"}}
        beh["workflows"]["Invitation"]["transitions"]["resume"] = {"from": ["paused"], "to": "in_management", "by": ["office"]}
        prop_dir = self.app / ".modeler" / "proposals"
        prop_dir.mkdir(parents=True, exist_ok=True)
        (prop_dir / "p1.json").write_text(json.dumps({"note": "pausa", "metamodel": meta, "behavior": beh}))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.cmd_proposals(argparse.Namespace(path=str(self.app))), 0)
        self.assertIn("behaviour: + state Invitation.paused", out.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.cmd_apply(argparse.Namespace(path=str(self.app), proposal=None, write=True)), 0)
        text = (self.app / "behavior.yaml").read_text()
        self.assertIn("+ transition Invitation.pause: in_management -> paused", out.getvalue())
        self.assertIn("3 comment line(s) of behavior.yaml are not kept", out.getvalue())        # the hand one and the header
        self.assertNotIn("~ derivation", out.getvalue())                                           # same formulas, written otherwise
        self.assertIn("paused: {label: {it: Sospeso, en: Paused}, owner: [office]}", text)
        self.assertIn("pause: {from: in_management, to: paused, by: [office], label: {it: Sospendi}}", text)
        self.assertNotIn("hand comment", text)
        self.assertTrue(any(f.name.startswith("behavior.yaml.") for f in (self.app / ".modeler" / "backups").iterdir()))
        self.assertIn('"paused"', (self.app / "src/lib/modeler/behavior.json").read_text())           # synced
        self.assertIn("`paused`", (self.app / "docs/BEHAVIOR.md").read_text())
        self.assertEqual(B.validate(B.load(self.app / "behavior.yaml"), E.load(self.app / "domain.ecore.yaml")).errors, [])
        # a behaviour that does not fit the metamodel is refused as a whole: nothing written
        beh["workflows"]["Invitation"]["transitions"]["pause"]["guard"] = "nope > 1"
        (self.app / "bad.json").write_text(json.dumps({"metamodel": meta, "behavior": beh}))
        before = text
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.cmd_apply(argparse.Namespace(path=str(self.app), proposal=str(self.app / "bad.json"), write=True)), 1)
        self.assertIn("not valid against its metamodel", out.getvalue())
        self.assertEqual((self.app / "behavior.yaml").read_text(), before)

    def test_apply_changes_only_the_changed_lines(self):
        # a proposal from production comes back from a jsonb column: keys sorted by length, then name
        def jsonb(v):
            return {k: jsonb(v[k]) for k in sorted(v, key=lambda k: (len(k), k))} if isinstance(v, dict) else v
        cli.install(self.app)
        meta_path = self.app / "domain.ecore.yaml"
        before = meta_path.read_text()
        doc = json.loads((self.app / "src/lib/modeler/metamodel.json").read_text())
        doc["classes"]["Persona"]["attributes"]["dataNascita"]["lower"] = 1
        (self.app / "p.json").write_text(json.dumps({"metamodel": jsonb(doc)}))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.cmd_apply(argparse.Namespace(path=str(self.app), proposal=str(self.app / "p.json"),
                                                              write=True)), 0)
        changed = [line for line in difflib.unified_diff(before.splitlines(), meta_path.read_text().splitlines(), n=0)
                   if line[:1] in "+-" and not line.startswith(("+++", "---"))]
        self.assertEqual(changed, ["-      dataNascita: Date", "+      dataNascita: {type: Date, lower: 1}"], changed)
        meta_path.write_text(meta_path.read_text().replace("classes:\n", "classes:  # curated by hand\n", 1))
        doc["classes"]["Persona"]["attributes"]["dataNascita"]["lower"] = 0
        (self.app / "p.json").write_text(json.dumps({"metamodel": jsonb(doc)}))
        with contextlib.redirect_stdout(io.StringIO()):
            cli.cmd_apply(argparse.Namespace(path=str(self.app), proposal=str(self.app / "p.json"), write=True))
        self.assertEqual(meta_path.read_text(), before.replace("classes:\n", "classes:  # curated by hand\n", 1))

    def test_apply_ignores_the_diagram_of_a_production_proposal(self):
        # the production editor saves box positions; the repository file has no diagram block
        def jsonb(v):
            return {k: jsonb(v[k]) for k in sorted(v, key=lambda k: (len(k), k))} if isinstance(v, dict) else v
        cli.install(self.app)
        meta_path = self.app / "domain.ecore.yaml"
        before = meta_path.read_text()
        doc = json.loads((self.app / "src/lib/modeler/metamodel.json").read_text())
        doc["classes"]["Persona"]["attributes"]["dataNascita"]["lower"] = 1
        doc["classes"]["Persona"]["attributes"]["attivo"]["lower"] = 1
        doc["diagram"] = {"Persona": {"x": 40, "y": 80}, "Soggetto": {"x": 300, "y": 80}}
        (self.app / "p.json").write_text(json.dumps({"metamodel": jsonb(doc)}))
        with contextlib.redirect_stdout(io.StringIO()):
            ns = argparse.Namespace(path=str(self.app), proposal=str(self.app / "p.json"), write=True, rewrite=False)
            self.assertEqual(cli.cmd_apply(ns), 0)
        after = meta_path.read_text()
        changed = [line for line in difflib.unified_diff(before.splitlines(), after.splitlines(), n=0)
                   if line[:1] in "+-" and not line.startswith(("+++", "---"))]
        self.assertEqual(len(changed), 4, changed)                          # two attributes, nothing else
        self.assertNotIn("diagram", after)

    def test_apply_stops_instead_of_rewriting_the_whole_file(self):
        cli.install(self.app)
        meta_path = self.app / "domain.ecore.yaml"
        before = meta_path.read_text()
        doc = json.loads((self.app / "src/lib/modeler/metamodel.json").read_text())
        doc["doc"] = "Another package description"                          # header: not editable line by line
        (self.app / "p.json").write_text(json.dumps({"metamodel": doc}))
        ns = argparse.Namespace(path=str(self.app), proposal=str(self.app / "p.json"), write=True, rewrite=False)
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            self.assertEqual(cli.cmd_apply(ns), 1)
        self.assertEqual(meta_path.read_text(), before)
        self.assertIn("--rewrite", err.getvalue())
        self.assertTrue((self.app / "p.json").exists())
        ns.rewrite = True
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.cmd_apply(ns), 0)
        self.assertIn("Another package description", meta_path.read_text())

@unittest.skipUnless(shutil.which("node"), "node not installed")
class EditorLayoutTests(unittest.TestCase):
    def test_layout_of_the_editor(self):
        # the layout rules of core:diagrams, checked on the editor's pure layout functions (layout.test.mjs)
        self.node_test("layout.test.mjs")

    def test_changes_of_a_proposal_match_the_cli(self):
        self.node_test("diff.test.mjs")

    def node_test(self, name):
        res = subprocess.run(["node", "--test", str(ROOT / "tests" / name)], capture_output=True, text=True, timeout=120)
        self.assertEqual(res.returncode, 0, res.stdout[-3000:] + res.stderr[-2000:])


class HookTests(unittest.TestCase):
    HOOK = ROOT / "hooks" / "hook.py"

    def run_hook(self, mode, payload):
        return subprocess.run([sys.executable, str(self.HOOK), mode], input=json.dumps(payload),
                              capture_output=True, text=True)

    def test_invalid_metamodel_is_sent_back(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "domain.ecore.yaml"
            f.write_text("package: t\nclasses:\n  A:\n    attributes: {x: Strin}\n")
            out = self.run_hook("post", {"tool_input": {"file_path": str(f)}})
            self.assertEqual(out.returncode, 2)
            self.assertIn("unknown data type", out.stderr)
            f.write_text(FIXTURE.read_text())
            self.assertEqual(self.run_hook("post", {"tool_input": {"file_path": str(f)}}).returncode, 0)

    def test_migration_reminder_and_session(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "domain.ecore.yaml").write_text(FIXTURE.read_text())
            mig = Path(d) / "supabase" / "migrations" / "20260101000000_x.sql"
            out = self.run_hook("post", {"tool_input": {"file_path": str(mig)}})
            self.assertIn("Update the metamodel", out.stdout)
            out = self.run_hook("session", {"cwd": d})
            self.assertIn("not installed", out.stdout)
            self.assertIn(f"Modeler plugin loaded in this session: {__version__}.", out.stdout)
            self.assertNotIn("not applied yet", out.stdout)
            props = Path(d) / ".modeler" / "proposals"
            (props / "applied").mkdir(parents=True)
            (props / "2026-10-15T10-00-00.json").write_text("{}")
            (props / "applied" / "old.json").write_text("{}")
            out = self.run_hook("session", {"cwd": d})
            self.assertIn("1 proposal(s) saved by the admin modeler and not applied yet", out.stdout)
            self.assertIn("2026-10-15T10-00-00.json", out.stdout)
            self.assertEqual(self.run_hook("session", {"cwd": tempfile.gettempdir()}).stdout, "")
            (Path(d) / "tools" / "modeler").mkdir(parents=True)
            (Path(d) / "tools" / "modeler" / "VERSION").write_text(__version__ + "\n")
            self.assertIn("docs/DOMAIN.md missing", self.run_hook("session", {"cwd": d}).stdout)
            (Path(d) / "docs").mkdir()
            (Path(d) / "docs" / "domain.md").write_text("# other\n")
            self.assertIn("docs/domain.md differs from docs/DOMAIN.md only by letter case",
                          self.run_hook("session", {"cwd": d}).stdout)
            (Path(d) / "docs" / "domain.md").unlink()
            cli.write_docs(Path(d), E.load(Path(d) / "domain.ecore.yaml"))
            self.assertNotIn("DOMAIN.md", self.run_hook("session", {"cwd": d}).stdout)
            md = Path(d) / "docs" / "DOMAIN.md"
            md.write_text(md.read_text() + "\n## Note\n\nx\n")
            out = self.run_hook("session", {"cwd": d})
            self.assertIn("hand edits", out.stdout)
            self.assertIn("Note (new)", out.stdout)
            out = self.run_hook("post", {"tool_input": {"file_path": str(md)}})
            self.assertEqual(out.returncode, 0)
            self.assertIn("generated from", out.stdout)


@unittest.skipUnless(os.environ.get("MODELER_PG"), "MODELER_PG not set")
class DatabaseTests(unittest.TestCase):
    SCHEMA = """
    create type booking_status as enum ('draft', 'confirmed');
    create table profiles (id uuid primary key);
    create table rooms (id uuid primary key default gen_random_uuid(), name varchar(80) not null unique, seats int,
      type text);
    create table bookings (id uuid primary key default gen_random_uuid(),
      room_id uuid not null references rooms(id) on delete restrict,
      owner_id uuid references profiles(id), status booking_status not null default 'draft',
      starts_on date not null, kind text check (kind in ('lesson', 'meeting')), notes text,
      created_at timestamptz not null default now());
    create table booking_items (id uuid primary key default gen_random_uuid(),
      booking_id uuid not null references bookings(id) on delete cascade, label text not null);
    create table tags (id uuid primary key default gen_random_uuid(), name text not null);
    create table bookings_tags (booking_id uuid references bookings(id) on delete cascade,
      tag_id uuid references tags(id) on delete cascade, primary key (booking_id, tag_id));
    """

    def setUp(self):
        self.base = os.environ["MODELER_PG"]
        self.db = f"modeler_{uuid.uuid4().hex[:8]}"
        subprocess.run(["psql", self.base, "-qc", f"create database {self.db}"], check=True, capture_output=True)
        self.dsn = self.base.rsplit("/", 1)[0] + "/" + self.db
        subprocess.run(["psql", self.dsn, "-q", "-v", "ON_ERROR_STOP=1", "-c", self.SCHEMA], check=True, capture_output=True)

    def tearDown(self):
        subprocess.run(["psql", self.base, "-qc", f"drop database {self.db} with (force)"], capture_output=True)

    def test_pull_apply_done(self):
        sql = (Path(__file__).resolve().parents[1] / "kit" / "model_change_requests.sql").read_text()
        sql = sql[:sql.index("alter table")]                                # no is_admin() outside Supabase
        subprocess.run(["psql", self.dsn, "-q", "-v", "ON_ERROR_STOP=1", "-c", sql], check=True, capture_output=True)
        with tempfile.TemporaryDirectory() as d:
            app = Path(d)
            (app / "domain.ecore.yaml").write_text(FIXTURE.read_text())
            meta = E.runtime_json(E.load(app / "domain.ecore.yaml"))
            meta["classes"]["Persona"]["attributes"]["telefono"] = {"type": "EString", "lower": 0, "upper": 1}
            subprocess.run(["psql", self.dsn, "-q", "-v", "ON_ERROR_STOP=1", "-c",
                            "insert into model_change_requests (metamodel, note) values "
                            f"('{json.dumps(meta)}'::jsonb, 'telefono'), ('{{}}'::jsonb, 'no'), "
                            f"('{json.dumps(meta)}'::jsonb, 'zz')"],
                           check=True, capture_output=True)
            status = lambda: subprocess.run(["psql", self.dsn, "-At", "-c", "select note || '=' || status from "  # noqa: E731
                                             "model_change_requests order by note"],
                                            capture_output=True, text=True).stdout.split()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(cli.cmd_pull(argparse.Namespace(path=str(app), db=self.dsn)), 0)
                self.assertEqual(status(), ["no=pulled", "telefono=pulled", "zz=pulled"])
                subprocess.run(["psql", self.dsn, "-qc", "update model_change_requests set status = 'rejected' "
                                "where note = 'zz'"], check=True)               # rejected from the production modeler
                props = sorted((app / ".modeler" / "proposals").glob("*.json"))
                tel = next(f for f in props if json.loads(f.read_text())["note"] == "telefono")
                zz = next(f for f in props if json.loads(f.read_text())["note"] == "zz")
                rej = next(f for f in props if json.loads(f.read_text())["note"] == "no")
                ns = argparse.Namespace(path=str(app), proposal=str(tel), write=True)
                self.assertEqual(cli.cmd_apply(ns), 0)
                (rej.parent / "rejected").mkdir()
                rej.rename(rej.parent / "rejected" / rej.name)               # rejected from the local modeler
                self.assertEqual(cli.cmd_done(argparse.Namespace(path=str(app), db=self.dsn, write=False)), 0)
                self.assertEqual(status(), ["no=pulled", "telefono=pulled", "zz=rejected"])   # dry run
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    self.assertEqual(cli.cmd_done(argparse.Namespace(path=str(app), db=self.dsn, write=True)), 0)
            self.assertEqual(status(), ["no=rejected", "telefono=applied", "zz=rejected"])
            self.assertIn("already 'rejected' in production", err.getvalue())    # zz was archived with telefono
            self.assertEqual(json.loads((app / ".modeler/proposals/applied" / zz.name).read_text())["closed"], "rejected")
            self.assertEqual(json.loads((app / ".modeler/proposals/applied" / tel.name).read_text())["closed"], "applied")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                cli.cmd_done(argparse.Namespace(path=str(app), db=self.dsn, write=True))
            self.assertIn("nothing to close", out.getvalue())

    def test_reverse_and_drift(self):
        cat = D.catalog(self.dsn)
        meta, notes = D.reverse(cat, package="aule")
        self.assertTrue(E.validate(meta).ok, E.validate(meta).render())
        e = E.expand(meta)
        b = e["classes"]["Booking"]
        self.assertEqual(b["attributes"]["status"]["type"], "BookingStatus")
        self.assertEqual(b["attributes"]["kind"]["type"], "Kind")
        self.assertIn("type", e["classes"]["Room"]["attributes"])            # an ordinary column name
        self.assertEqual(b["references"]["room"]["column"], "room_id")
        self.assertEqual(b["references"]["owner"]["type"], "User")
        self.assertTrue(b["references"]["bookingItems"]["containment"])
        self.assertEqual(b["references"]["tags"]["join_table"], "bookings_tags")
        self.assertEqual(D.drift(meta, cat), [])
        e["classes"]["Room"]["attributes"]["floor"] = {"type": "EInt", "lower": 0, "upper": 1}
        e["classes"]["Room"]["attributes"]["seats"]["lower"] = 1
        found = D.drift(E.compact(e), cat)
        self.assertIn("MISSING COLUMN rooms.floor (Room.floor)", found)
        self.assertTrue(any(x.startswith("NULLABLE rooms.seats") for x in found), found)

    def test_exclude_columns(self):
        cat = D.catalog(self.dsn)
        meta, _ = D.reverse(cat, package="aule", exclude={"rooms.seats"})
        self.assertNotIn("seats", E.expand(meta)["classes"]["Room"]["attributes"])
        self.assertIn("NOT IN METAMODEL rooms: columns seats", D.drift(meta, cat))
        self.assertEqual(D.drift(meta, cat, {"rooms.seats"}), [])
        self.assertEqual(D.split_exclude({"events", "rooms.seats"}), ({"events"}, {("rooms", "seats")}))

    def psql(self, sql):
        out = subprocess.run(["psql", self.dsn, "-q", "-v", "ON_ERROR_STOP=1"], input=sql, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)

    def test_generated_migrations_apply_and_align(self):
        meta = E.load(FIXTURE)
        sql, _ = G.migration({"package": "t", "classes": {}}, meta)
        self.psql(sql)
        other = {"rooms", "bookings", "booking_items", "tags", "bookings_tags"}   # the schema of setUp
        self.assertEqual(D.drift(meta, D.catalog(self.dsn), other), [])
        self.psql("insert into gruppi (id, nome) values (gen_random_uuid(), 'g');")   # data survives the evolution
        new = _evolved(meta)
        step, _ = G.migration(meta, new)
        self.psql(step)
        found = D.drift(new, D.catalog(self.dsn), other)
        # only the reviewed parts remain: the required column still nullable, the dropped column still there
        self.assertEqual(sorted(x.split(":")[0] for x in found),
                         ["NOT IN METAMODEL gruppi", "NULLABLE persone.matricola"], found)
        # a Postgres enum type gets the new literal too
        self.psql("create type public.stato as enum ('bozza');")
        with_type = {"package": "t", "classes": {"Pratica": {"attributes": {"x": "EString"}}}, "enums": {"Stato": ["BOZZA"]}}
        later = copy.deepcopy(with_type)
        later["classes"]["Pratica"]["attributes"]["stato"] = "Stato"
        prev = copy.deepcopy(later)
        later["enums"]["Stato"] = ["BOZZA", "CHIUSA"]
        self.psql("create table pratiche (id uuid primary key, x text, stato public.stato);")
        self.psql(G.migration(prev, later)[0])
        out = subprocess.run(["psql", self.dsn, "-At", "-c", "select string_agg(enumlabel, ',' order by enumsortorder) "
                              "from pg_enum e join pg_type t on t.oid = e.enumtypid where t.typname = 'stato'"],
                             capture_output=True, text=True)
        self.assertEqual(out.stdout.strip(), "bozza,chiusa")


    def test_unique_together_applies_aligns_and_rejects_a_second_default(self):
        meta = _tariffs()
        self.psql(G.migration({"package": "t", "classes": {}}, meta)[0])
        other = {"rooms", "bookings", "booking_items", "tags", "bookings_tags"}
        cat = D.catalog(self.dsn)
        self.assertEqual(D.drift(meta, cat, other), [])
        rev, _ = D.reverse(cat, package="tariffe", exclude=other)
        tariffa = next(c for c in E.expand(rev)["classes"].values() if c.get("table") == "tariffe")
        self.assertEqual(tariffa["unique"], [["voce", "motivo", "posizione"]])
        row = "insert into tariffe (voce, motivo) select id, 'nascita' from voci;"
        self.psql("insert into voci (id, nome) values (gen_random_uuid(), 'v');" + row)
        out = subprocess.run(["psql", self.dsn, "-q", "-v", "ON_ERROR_STOP=1"], input=row, capture_output=True, text=True)
        self.assertIn("tariffe_voce_motivo_posizione_key", out.stderr)    # the default row cannot be repeated

if __name__ == "__main__":
    unittest.main()
