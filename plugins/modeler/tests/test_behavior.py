"""The behaviour model (behavior.yaml) checked against the domain metamodel: expressions, principals,
workflows, derivations, events, reactions, subscriptions; the CLI and the hook that run the check.

python3 -m unittest discover -s plugins/modeler/tests
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from metamodel import behavior as B  # noqa: E402
from metamodel import cli  # noqa: E402
from metamodel import core as M  # noqa: E402
from metamodel import dbschema as D  # noqa: E402
from metamodel import ecore as E  # noqa: E402
from metamodel import expr as X  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
META = FIXTURES / "invitations.ecore.yaml"
BEHAVIOR = FIXTURES / "invitations.behavior.yaml"


def meta() -> dict:
    return E.load(META)


def behavior() -> dict:
    return B.load(BEHAVIOR)


def errors(b: dict, m: dict | None = None) -> list[str]:
    return B.validate(b, m if m is not None else meta()).errors


class ExpressionTests(unittest.TestCase):
    def setUp(self):
        self.e = E.expand(meta())
        self.ctx = X.Context(self.e, "Invitation")

    def check(self, text, expect=None):
        return X.check(text, self.ctx, expect)

    def fails(self, text, fragment, ctx=None):
        with self.assertRaises(X.ExprError) as cm:
            X.check(text, ctx or self.ctx)
        self.assertIn(fragment, str(cm.exception))

    def test_paths_literals_and_operators(self):
        self.assertEqual(self.check("dataComplete")[1], X.BOOL)
        self.assertEqual(self.check("self.dataComplete", X.BOOL)[1], X.BOOL)
        self.assertEqual(self.check("reason.compensationType = hourly and hours > 0")[1], X.BOOL)
        self.assertEqual(self.check("hourly = compensationType")[1], X.BOOL)      # the literal on either side
        self.assertEqual(self.check("invitationFunds.amount.sum() = totalAmount")[1], X.BOOL)
        self.assertEqual(self.check("invitationFunds.size() >= 1 and invitationFunds.notEmpty()")[1], X.BOOL)
        self.assertEqual(self.check("not (travelMethod in [agency, none]) or state = 'draft'")[1], X.BOOL)
        self.assertEqual(self.check("startDate < endDate and hours >= 1.5 and notes.isEmpty()")[1], X.BOOL)
        self.assertEqual(self.check("self.guest.email")[1], "email")
        self.assertEqual(self.check("department.createdBy")[1], X.CLASS + "User")
        self.assertEqual(self.check("department.createdBy.email")[1], "email")
        self.assertEqual(self.check("invitationFunds.fund")[1], X.COLLECTION + X.CLASS + "Fund")
        self.assertEqual(self.check("self")[1], X.CLASS + "Invitation")

    def test_type_errors(self):
        self.fails("compensationType = bogus", "not a literal of enum CompensationType (hourly, flat, none)")
        self.fails("startDate < hours", "cannot compare date with number")
        self.fails("hours > 'x'", "cannot compare number with string")
        self.fails("reason = guest", "cannot compare a reference")
        self.fails("invitationFunds = 3", "cannot compare a collection")
        self.fails("invitationFunds.isSet()", "isSet() tests a single value")
        self.fails("hours.notEmpty()", "notEmpty() needs a collection")
        self.fails("hours.size()", "size() needs a collection")
        self.fails("invitationFunds.fund.sum()", "sum() needs a collection of numbers")
        self.fails("reason.economicRates.position.economicRates", "collection of collections")
        self.assertEqual(self.check("invitationFunds.fund.createdBy")[1], X.COLLECTION + X.CLASS + "User")
        self.fails("department.createdBy.name", "User is built in: only 'email'")
        self.fails("hours and dataComplete", "'and' needs booleans, found number")
        self.fails("not hours", "'not' needs a boolean")
        self.fails("state > 'a'", "'>' needs numbers or dates")
        self.fails("accommodationMethod in [agency, 3]", "cannot compare enum AccommodationMethod with int")
        self.fails("nope", "'nope' is not a feature of Invitation (a bare name is an enum literal only")
        self.fails("reason.nope", "'nope' is not a feature of InvitationReason")
        self.fails("hours.nope", "'hours' is number: it has no feature 'nope'")
        self.fails("hours.round()", "unknown operation round()")
        with self.assertRaises(X.ExprError) as cm:
            self.check("hours", X.BOOL)
        self.assertIn("expected bool, found number", str(cm.exception))

    def test_syntax_errors_carry_the_position(self):
        for text, fragment in [("hours >", "unexpected end of expression"), ("(hours > 1", "expected ')'"),
                               ("hours > 1 2", "unexpected '2'"), ("hours in []", "empty list"),
                               ("hours ! 1", "unexpected character '!'"), ("", "empty expression")]:
            with self.assertRaises(X.ExprError) as cm:
                X.parse(text)
            self.assertIn(fragment, str(cm.exception), text)
        with self.assertRaises(X.ExprError) as cm:
            X.parse("hours > 1 2")
        self.assertEqual(cm.exception.pos, 10)

    def test_variables_of_a_reaction(self):
        ctx = X.Context(self.e, "Invitation", {"transition": X.ENUM + "@transition"}, {"@transition": ["submit", "close"]})
        self.assertEqual(X.check("transition = submit", ctx)[1], X.BOOL)
        self.assertEqual(X.check("transition in [submit, close] and dataComplete", ctx)[1], X.BOOL)
        self.fails("transition = approve", "'approve' is not a literal of one of the names (submit, close)", ctx)
        self.fails("transition = submit", "'transition' is not a feature of Invitation")

    def test_text_round_trip_and_features_used(self):
        node, _ = self.check("not (a_or_b or dataComplete) and reason.compensationType in [hourly, flat]"
                             .replace("a_or_b", "agencyBookingRequired"))
        self.assertEqual(X.to_text(node), "not (agencyBookingRequired or dataComplete) and reason.compensationType in [hourly, flat]")
        self.assertEqual(X.features_used(node), [("Invitation", "agencyBookingRequired"), ("Invitation", "dataComplete"),
                                                 ("Invitation", "reason", "compensationType")])
        # every hop attributed to the class that owns the feature (features_used keeps the context class only)
        self.assertEqual(X.hops_used(node), [("Invitation", "agencyBookingRequired"), ("Invitation", "dataComplete"),
                                             ("Invitation", "reason"), ("InvitationReason", "compensationType")])
        node, _ = self.check("invitationFunds.amount.sum() > 0 and guest.email.isSet()")
        self.assertEqual(X.hops_used(node), [("Invitation", "invitationFunds"), ("InvitationFund", "amount"),
                                             ("Invitation", "guest"), ("Guest", "email")])
        self.assertEqual(X.hops_used(X.check("transition = submit", X.Context(self.e, "Invitation", {"transition": X.ENUM + "@transition"},
                                                                                {"@transition": ["submit"]}))[0]), [])
        node, _ = self.check("state = 'it''s'".replace("''", "\\'"))
        self.assertEqual(X.to_text(X.parse(X.to_text(node))), X.to_text(node))


class BehaviorTests(unittest.TestCase):
    def test_fixture_is_valid(self):
        rep = B.validate(behavior(), meta())
        self.assertEqual((rep.errors, rep.warnings), ([], []))
        # a derived attribute without a formula is computed in code: reported, not refused
        b = behavior()
        b["derivations"]["Invitation"].pop("fundsTotal")
        rep = B.validate(b, meta())
        self.assertEqual(rep.errors, [])
        self.assertEqual([w.split(":")[0] for w in rep.warnings], ["derivations.Invitation.fundsTotal"])
        b = B.expand(behavior())
        self.assertEqual(b["workflows"]["Invitation"]["transitions"]["withdraw"]["from"], ["draft", "rejected"])
        self.assertEqual(b["workflows"]["Invitation"]["transitions"]["submit"]["from"], ["draft"])
        self.assertEqual(b["workflows"]["Invitation"]["states"]["awaiting_confirmation"]["reminder"]["after"], "7d")
        self.assertEqual(B.events_of(b, "Invitation"), ["created", "updated", "deleted", "transitioned", "completed",
                                                          "reverted", "reminder", "visit_ended"])
        self.assertEqual(B.events_of(b, "Guest"), ["created", "updated", "deleted"])

    def test_a_domain_change_breaks_the_behaviour(self):
        m = meta()
        attrs = m["classes"]["Invitation"]["attributes"]
        attrs["visitEnd"] = attrs.pop("endDate")                     # a rename in the metamodel
        errs = errors(behavior(), m)
        self.assertTrue(any("transitions.visit_ended.at" in x and "'endDate' is not a feature" in x for x in errs), errs)
        m = meta()
        m["classes"]["Invitation"]["references"].pop("reason")
        errs = errors(behavior(), m)
        self.assertTrue(any("derivations.Invitation.dataComplete" in x and "'reason' is not a feature" in x for x in errs), errs)
        self.assertTrue(any("derivations.Invitation.compensationType" in x for x in errs))
        m = meta()
        m["classes"]["Invitation"]["references"].pop("issuer")      # principals navigate too
        errs = errors(behavior(), m)
        self.assertTrue(any("states.draft.owner" in x and "self.issuer" in x for x in errs), errs)
        self.assertTrue(any("notify_approved" in x and "self.issuer" in x for x in errs), errs)
        m = meta()
        m["enums"]["CompensationType"] = ["hourly", "none"]          # a literal used by a derivation disappears
        errs = errors(behavior(), m)
        self.assertTrue(any("dataComplete: 'flat' is not a literal of enum CompensationType (hourly, none)" in x for x in errs), errs)
        m = meta()
        m["classes"]["Guest"]["attributes"]["email"] = {"type": "EString", "lower": 1}
        errs = errors(behavior(), m)
        self.assertTrue(any("notify_bookings_guest" in x and "self.guest.email' is string" in x for x in errs), errs)

    def test_recipients_travel_on_the_transition_event(self):
        self.assertEqual(B.validate(behavior(), meta()).warnings, [])
        b = behavior()
        b["events"]["Invitation"]["assigned"] = {}
        b["workflows"]["Invitation"]["transitions"]["approve"]["emits"] = ["assigned"]
        b["reactions"].append({"name": "notify_assigned", "event": "Invitation.assigned", "notify": ["office"], "template": "assigned"})
        b["templates"]["assigned"] = {"it": {"subject": "Assegnato", "body": "{{transition.label}}"}}
        w = [x for x in B.validate(b, meta()).warnings if "notify_assigned" in x]
        self.assertEqual(len(w), 2, w)
        self.assertIn("recipients on Invitation.assigned, a secondary event of transition `approve`", w[0])
        self.assertIn("`when: transition = approve`", w[0])
        self.assertIn("notifies on both Invitation.transitioned (notify_to_manage, notify_approved) and Invitation.assigned", w[1])
        # the secondary event without recipients carries data only: fine
        b["reactions"].pop()
        b["templates"].pop("assigned")
        self.assertEqual(B.validate(b, meta()).warnings, [])
        # a reaction with recipients on an event no subscription receives
        b = behavior()
        b["subscriptions"][0]["events"] = ["Invitation.transitioned", "Guest.*"]
        w = [x for x in B.validate(b, meta()).warnings if "notify_reverted" in x]
        self.assertEqual(len(w), 1, w)
        self.assertIn("notifies on Invitation.reverted but no subscription receives it", w[0])
        self.assertEqual(B.transition_reactions(B.expand(behavior()), E.expand(meta()), "Invitation")["submit"], ["notify_submitted"])

    def test_notification_templates_are_checked_against_the_model(self):
        # the fixture: texts for every template, placeholders on the record and the event
        rep = B.validate(behavior(), meta())
        self.assertEqual((rep.errors, rep.warnings), ([], []))
        b = behavior()
        self.assertEqual(sorted(B.template_uses(B.expand(b))["invitation_submitted"]),
                         [("Invitation", "transitioned", "reaction notify_submitted")])
        self.assertIn("reminder.days", B.template_variables(B.expand(b), "Invitation", "reminder"))
        self.assertNotIn("transition.label", B.template_variables(B.expand(b), "Invitation", "reverted"))
        # the texts use {{url}}: the app defines record_url (drift checks the database for it)
        self.assertTrue(B.uses_url(b))
        for langs in b["templates"].values():
            for tx in langs.values():
                tx["body"] = tx["body"].replace("{{url}}", "")
        self.assertFalse(B.uses_url(b))
        b = behavior()
        # a template a reaction names but no texts for it
        b["templates"].pop("invitation_closed")
        w = [x for x in B.validate(b, meta()).warnings if "invitation_closed" in x]
        self.assertEqual(len(w), 1)
        self.assertIn("no texts for template `invitation_closed` (used by reaction notify_closed)", w[0])
        # placeholders: unknown path, collection, event variable on the wrong event, unknown name; a missing language
        b = behavior()
        b["templates"]["invitation_rejected"]["it"]["body"] = "{{self.nope}} {{self.invitationFunds}} {{reminder.days}} {{boh}}"
        b["templates"]["invitation_reverted"]["it"]["subject"] = "{{transition.label}}"
        b["templates"]["invitation_closed"].pop("en")                         # the metamodel's language is en
        rep = B.validate(b, meta())
        errs = "\n".join(rep.errors)
        for frag in ["templates.invitation_rejected.it.body: {{self.nope}}: 'nope' is not a feature of Invitation",
                     "{{self.invitationFunds}}: a collection", "{{reminder.days}}: reminder.* only on <Class>.reminder",
                     "{{boh}}: unknown placeholder", "templates.invitation_reverted.it.subject: {{transition.label}}: transition.* only on"]:
            self.assertIn(frag, errs, frag)
        self.assertTrue(any("templates.invitation_closed: no texts in the language of the metamodel (en)" in x for x in rep.warnings), rep.warnings)
        # an unused template, a bad language, a missing subject
        b = behavior()
        b["templates"]["orphan"] = {"english": {"body": "x"}}
        rep = B.validate(b, meta())
        self.assertTrue(any("templates.orphan: not used" in x for x in rep.warnings))
        self.assertTrue(any("templates.orphan.english: a language code" in x for x in rep.errors))
        self.assertTrue(any("templates.orphan.english: subject" in x for x in rep.errors))
        # the texts travel into behavior.json, BEHAVIOR.md, the YAML writer, the editor round trip and the diff
        rt = B.runtime_json(behavior(), meta())
        self.assertEqual(rt["templates"]["invitation_submitted"]["it"]["subject"], "Invito {{self.id}} da approvare")
        md = B.to_markdown(behavior(), meta())
        self.assertIn("## Notification texts", md)
        self.assertIn("| `invitation_submitted` | it | Invito {{self.id}} da approvare | {{actor.email}} ha emesso un invito ({{transition.label}}). Dettagli: {{url}} |", md)
        again = B.loads(B.dumps(behavior()))
        self.assertEqual(B.expand(again)["templates"], B.expand(behavior())["templates"])
        self.assertEqual(B.expand(B.from_editor(rt))["templates"], B.expand(behavior())["templates"])
        b = behavior()
        b["templates"]["invitation_closed"]["en"]["subject"] = "Closed!"
        b["templates"].pop("invitation_reverted")
        b["templates"]["extra"] = {"it": {"subject": "x", "body": "y"}}
        self.assertEqual(sorted(x for x in B.diff(behavior(), b) if "template" in x),
                         ["+ template extra (it)", "- template invitation_reverted", "~ template invitation_closed: en"])

    def test_collection_multiplicities_are_enforced_by_a_guard_or_reported(self):
        # the fixture: Invitation.invitationFunds is 1..* and dataComplete (a guard of submit) reads it: nothing to say
        self.assertEqual(B.validate(behavior(), meta()).warnings, [])
        b = behavior()
        b["derivations"]["Invitation"]["dataComplete"] = "reason.isSet()"
        w = [x for x in B.validate(b, meta()).warnings if x.startswith("Invitation.invitationFunds")]
        self.assertEqual(len(w), 1)
        self.assertIn("minimum of the collection (1..*) not enforced", w[0])
        self.assertIn("invitationFunds.notEmpty()", w[0])
        # a guard that reads the collection directly is enough
        b["workflows"]["Invitation"]["transitions"]["submit"]["guard"] = "dataComplete and invitationFunds.size() >= 1"
        self.assertEqual([x for x in B.validate(b, meta()).warnings if x.startswith("Invitation.invitationFunds")], [])
        # a finite maximum is stored as many: the metamodel's validate says the model does not enforce it
        m = meta()
        m["classes"]["Invitation"]["references"]["invitationFunds"]["upper"] = 3
        w = [x for x in E.validate(m).warnings if "invitationFunds" in x]
        self.assertEqual(len(w), 1)
        self.assertIn("finite maximum (upper: 3) is stored as many", w[0])
        self.assertEqual(E.expand(m)["classes"]["Invitation"]["references"]["invitationFunds"]["upper"], -1)
        # a class without a workflow: the minimum is a rule of the application
        m = meta()
        m["classes"]["Department"]["references"]["guests"] = {"type": "Guest", "lower": 1, "upper": -1}
        w = [x for x in B.validate(behavior(), m).warnings if x.startswith("Department.guests")]
        self.assertEqual(len(w), 1)
        self.assertIn("no workflow", w[0])

    def test_fields_required_from_a_state(self):
        # `requires` on a state: set (a collection: not empty) to enter the state and while the record is there
        b = behavior()
        m = meta()
        m["classes"]["Invitation"]["references"]["reason"]["lower"] = 0            # optional in the metamodel …
        b["workflows"]["Invitation"]["states"]["pending_director"]["requires"] = ["reason", "hours"]  # … required from here
        rep = B.validate(b, m)
        self.assertEqual((rep.errors, rep.warnings), ([], []))
        x = B.expand(b)["workflows"]["Invitation"]["states"]
        self.assertEqual(x["pending_director"]["requires"], ["reason", "hours"])
        self.assertEqual(x["draft"]["requires"], [])
        self.assertEqual(B.requires_tests(E.expand(m), "Invitation", x["pending_director"]), [("reason", "reason.isSet()"), ("hours", "hours.isSet()")])
        u = B.uses(B.expand(b), E.expand(m))["Invitation"]
        self.assertIn({"kind": "requires", "of": "Invitation.pending_director"}, u["references"]["reason"])
        self.assertIn({"kind": "requires", "of": "Invitation.pending_director"}, u["attributes"]["hours"])
        v = B.engine_version(b, m, "Invitation")
        self.assertEqual(next(st["requires"] for st in v["states"] if st["key"] == "pending_director"), ["reason", "hours"])
        self.assertEqual(next(st["requires"] for st in v["states"] if st["key"] == "draft"), [])
        md = B.to_markdown(b, m, "en")
        self.assertIn("| State | Label | Kind | Waiting for | Editable by | Requires | Reminder |", md)
        self.assertIn("| `pending_director` | Awaiting approval |  | `director` |  | `reason`, `hours` |  |", md)
        sql = B.sql_view(b, m)
        self.assertIn("--   pending_director.requires: reason, hours (to enter the state, and while the record is there)", sql)
        self.assertIn("coalesce(r.reason is not null, false)  -- reason", sql)
        self.assertIn("coalesce(r.hours is not null, false)  -- hours", sql)
        self.assertEqual(B.diff(behavior(), b), ["~ state Invitation.pending_director: requires"])
        # a collection: the state requires it not empty, which also enforces its minimum (no guard needed)
        b = behavior()
        b["derivations"]["Invitation"]["dataComplete"] = "reason.isSet()"
        b["workflows"]["Invitation"]["states"]["pending_director"]["requires"] = ["invitationFunds"]
        w = [x for x in B.validate(b, meta()).warnings if "invitationFunds" in x]
        self.assertEqual(w, ["workflows.Invitation.states.pending_director.requires: 'invitationFunds' is already required by the metamodel (lower 1): the state adds nothing"])
        m = meta()
        m["classes"]["Invitation"]["references"]["invitationFunds"]["lower"] = 0
        self.assertEqual([x for x in B.validate(b, m).warnings if "invitationFunds" in x], [])
        self.assertEqual(B.requires_tests(E.expand(m), "Invitation", B.expand(b)["workflows"]["Invitation"]["states"]["pending_director"]),
                         [("invitationFunds", "invitationFunds.notEmpty()")])
        # errors: unknown feature, the state attribute, a derived attribute, a name listed twice
        b = behavior()
        b["workflows"]["Invitation"]["states"]["payment"]["requires"] = ["ghost", "state", "dataComplete", "hours", "hours"]
        errs = errors(b)
        where = "workflows.Invitation.states.payment.requires"
        self.assertIn(f"{where}: 'ghost' is not a feature of Invitation", errs)
        self.assertIn(f"{where}: 'state' is the state attribute", errs)
        self.assertTrue(any(x.startswith(f"{where}: 'dataComplete' is derived") for x in errs), errs)
        self.assertIn(f"{where}: 'hours' listed twice", errs)
        # warnings: required from the initial state (that is lower: 1), a guard that repeats the test
        b = behavior()
        b["workflows"]["Invitation"]["states"]["draft"]["requires"] = ["hours"]
        b["workflows"]["Invitation"]["states"]["payment"]["requires"] = ["hours"]
        b["workflows"]["Invitation"]["transitions"]["director_confirm"]["guard"] = "dataComplete and hours.isSet()"
        rep = B.validate(b, meta())
        self.assertEqual(rep.errors, [])
        self.assertIn("workflows.Invitation.states.draft.requires: 'hours' required from the initial state: that is `lower: 1` in the metamodel (required from creation)", rep.warnings)
        self.assertIn("workflows.Invitation.states.payment.requires: the guard of `director_confirm` repeats hours: `requires` already checks them on entering payment", rep.warnings)
        # a single name is accepted as a list; dumps writes the key back
        b = behavior()
        b["workflows"]["Invitation"]["states"]["payment"]["requires"] = "hours"
        self.assertEqual(errors(b), [])
        self.assertIn("requires: hours}", B.dumps(b))
        b["workflows"]["Invitation"]["states"]["payment"]["requires"] = ["hours", "flatAmount"]
        self.assertIn("requires: [hours, flatAmount]}", B.dumps(b))

    def test_state_model_the_class_as_seen_from_a_state(self):
        # `model` of a state: a restrictive overlay on the class (lower, readonly, hidden, in); `requires` = lower: 1
        b = behavior()
        m = meta()
        st = b["workflows"]["Invitation"]["states"]
        st["pending_director"]["requires"] = ["hours"]
        st["pending_director"]["model"] = {"flatAmount": {"lower": 1, "readonly": True}, "notes": {"hidden": True},
                                           "travelMethod": {"in": ["agency", "receipts"]}}
        rep = B.validate(b, m)
        self.assertEqual((rep.errors, rep.warnings), ([], []))
        x = B.expand(b)["workflows"]["Invitation"]["states"]["pending_director"]
        self.assertEqual(x["model"]["notes"], {"lower": None, "readonly": False, "hidden": True, "in": None})
        ov = B.state_overlay(x)
        self.assertEqual(ov["hours"], {"lower": 1, "readonly": False, "hidden": False, "in": None})
        self.assertEqual(ov["flatAmount"], {"lower": 1, "readonly": True, "hidden": False, "in": None})
        self.assertEqual(ov["notes"], {"lower": None, "readonly": True, "hidden": True, "in": None})   # hidden implies read only
        self.assertEqual(ov["travelMethod"]["in"], ["agency", "receipts"])
        self.assertEqual(B.required_features(x), ["hours", "flatAmount"])
        self.assertEqual(B.requires_tests(E.expand(m), "Invitation", x), [("hours", "hours.isSet()"), ("flatAmount", "flatAmount.isSet()")])
        u = B.uses(B.expand(b), E.expand(m))["Invitation"]["attributes"]
        of = "Invitation.pending_director"
        self.assertIn({"kind": "requires", "of": of}, u["flatAmount"])
        self.assertIn({"kind": "readonly", "of": of}, u["flatAmount"])
        self.assertIn({"kind": "hidden", "of": of}, u["notes"])
        self.assertIn({"kind": "allowed", "of": of}, u["travelMethod"])
        # refine: the metamodel as seen from the state (MM_s)
        r = B.refine(m, "Invitation", x)
        c = r["classes"]["Invitation"]["attributes"]
        self.assertNotIn("notes", c)
        self.assertEqual((c["flatAmount"]["lower"], c["flatAmount"]["changeable"]), (1, False))
        self.assertEqual((c["hours"]["lower"], c["travelMethod"]["in"]), (1, ["agency", "receipts"]))
        emf = E.to_emfatic(r)
        self.assertIn("  readonly attr EBigDecimal[1] flatAmount;", emf)
        self.assertIn("  attr EBigDecimal[1] hours;", emf)
        self.assertIn('  attr TravelMethod[1] travelMethod = "none";  // in: agency, receipts', emf)
        self.assertNotIn("notes", emf.split("class Invitation")[1].split("}")[0])
        self.assertIn("  attr Text notes;", E.to_emfatic(m))                                   # the metamodel itself is untouched
        # the feature × state table of BEHAVIOR.md, the matrix behind it
        mx = B.state_matrix(B.expand(b), E.expand(m), "Invitation")
        self.assertEqual([row["feature"] for row in mx], ["hours", "flatAmount", "travelMethod", "notes"])     # class order
        self.assertEqual(list(mx[1]["states"]), ["pending_director"])
        md = B.to_markdown(b, m, "en")
        self.assertIn("| `pending_director` | Awaiting approval |  | `director` |  | `hours`, `flatAmount` |  |", md)
        self.assertIn("### The class as seen from each state", md)
        self.assertIn("| `flatAmount` |  | ● 🔒 |  |  |  |  |  |  |  |  |  |", md)
        self.assertIn("| `notes` |  | ○ |", md)
        self.assertIn("| `travelMethod` |  | {agency, receipts} |", md)
        self.assertIn("### Il metamodello per stato", B.to_markdown(b, m, "it"))
        self.assertNotIn("### The class as seen from each state", B.to_markdown(behavior(), m, "en"))   # no overlay: no table
        v = B.engine_version(b, m, "Invitation")
        sv = next(s for s in v["states"] if s["key"] == "pending_director")
        self.assertEqual(sv["requires"], ["hours", "flatAmount"])
        self.assertEqual(sv["model"]["notes"], {"lower": None, "readonly": True, "hidden": True, "in": None})
        self.assertEqual(next(s for s in v["states"] if s["key"] == "draft")["model"], {})
        sql = B.sql_view(b, m)
        self.assertIn("coalesce(r.travel_method is null or r.travel_method in ('agency', 'receipts'), false)  -- travelMethod", sql)
        self.assertIn("--   pending_director: read only: flatAmount, notes (an update that changes them is refused while the record is there)", sql)
        self.assertIn("new.flat_amount is distinct from old.flat_amount  -- flatAmount", sql)
        self.assertIn("coalesce(r.flat_amount is not null, false)  -- flatAmount", sql)
        self.assertEqual(B.diff(behavior(), b), ["~ state Invitation.pending_director: requires, model"])
        self.assertEqual(B.state_overlay(B.loads(B.dumps(b))["workflows"]["Invitation"]["states"]["pending_director"]), ov)   # round trip
        self.assertIn("requires: [hours], model: {flatAmount: {lower: 1, readonly: true}, notes: {hidden: true}", B.dumps(b))
        # docs/DOMAIN.md: the multiplicity and the notes carry the states
        anns = B.domain_annotations(b, m)
        ann = anns["Invitation"]
        self.assertEqual(ann["flatAmount"], [{"state": "pending_director", "label": {"it": "In attesa di approvazione", "en": "Awaiting approval"},
                                              "lower": 1, "readonly": True, "hidden": False, "in": None}])
        dm = E.to_markdown(m, "en", anns)
        self.assertIn("| flatAmount | EBigDecimal | 0..1 · 1 from Awaiting approval | read only from Awaiting approval |  |", dm)
        self.assertIn("| hours | EBigDecimal | 0..1 · 1 from Awaiting approval |  |  |", dm)
        self.assertIn("| notes | Text | 0..1 | hidden from Awaiting approval |  |", dm)
        self.assertIn("| travelMethod | TravelMethod | 1 | default none, {agency, receipts} from Awaiting approval |  |", dm)
        it = E.to_markdown(m, "it", anns)
        self.assertIn("| flatAmount | EBigDecimal | 0..1 · 1 da In attesa di approvazione | sola lettura da In attesa di approvazione |  |", it)
        self.assertEqual(E.to_markdown(m, "en"), E.to_markdown(m, "en", {}))
        # errors
        b = behavior()
        st = b["workflows"]["Invitation"]["states"]
        st["payment"]["model"] = {"ghost": {"lower": 1}, "state": {"readonly": True}, "dataComplete": {"lower": 1},
                                  "totalAmount": {"readonly": True}, "fundsTotal": {"hidden": True}, "hours": {"lower": 2},
                                  "department": {"lower": 0}, "notes": {"hidden": True, "lower": 1}, "flatAmount": {"in": ["x"]},
                                  "travelMethod": {"in": ["plane"]}, "accommodationMethod": {"in": []}, "code": {"bogus": 1},
                                  "justification": "required"}
        errs = errors(b)
        where = "workflows.Invitation.states.payment.model"
        for expected in (f"{where}.ghost: 'ghost' is not a feature of Invitation",
                         f"{where}.state: 'state' is the state attribute",
                         f"{where}.totalAmount: 'totalAmount' is derived: already read only",
                         f"{where}.hours: lower: 0 or 1 (a state requires a feature or leaves it as the metamodel says)",
                         f"{where}.department: 'department' is required by the metamodel (lower 1): a state cannot relax it",
                         f"{where}.notes: 'notes' hidden and required: a hidden feature cannot be set",
                         f"{where}.flatAmount: in: only for a single-valued enum attribute ('flatAmount' is EBigDecimal)",
                         f"{where}.travelMethod: in: not literals of TravelMethod: plane",
                         f"{where}.accommodationMethod: in: at least one literal",
                         f"{where}.code: unknown keys: bogus (allowed: hidden, in, lower, readonly)",
                         f"{where}.justification: a mapping: {{lower: 1, readonly: true, hidden: true, in: [a, b]}}"):
            self.assertIn(expected, errs)
        self.assertTrue(any(x.startswith(f"{where}.dataComplete: 'dataComplete' is derived") for x in errs), errs)
        self.assertFalse(any("fundsTotal" in x for x in errs), errs)                      # a derived attribute can be hidden
        # warnings: what the engine cannot enforce or the metamodel already says
        b = behavior()
        m = meta()
        m["classes"]["Invitation"]["attributes"]["justification"] = {"type": "EString", "changeable": False}
        b["workflows"]["Invitation"]["states"]["payment"]["model"] = {
            "invitationFunds": {"hidden": True}, "travelMethod": {"in": ["agency", "receipts", "flat", "none"]},
            "department": {"lower": 1}, "justification": {"readonly": True}}
        rep = B.validate(b, m)
        self.assertEqual(rep.errors, [])
        for expected in (f"{where}.invitationFunds: 'invitationFunds' is a collection: hidden is not enforced by the engine (its parts have their own table), only reported to the application",
                         f"{where}.travelMethod: in: all the literals of TravelMethod: the state adds nothing",
                         f"{where}.department: 'department' is already required by the metamodel (lower 1): the state adds nothing",
                         f"{where}.justification: 'justification' is already read only in the metamodel (changeable: false): the state adds nothing"):
            self.assertIn(expected, rep.warnings)
        # along the path: what a target state asks must be settable in the source state
        b = behavior()
        st = b["workflows"]["Invitation"]["states"]
        st["bookings"]["model"] = {"flatAmount": {"readonly": True}, "travelMethod": {"readonly": True, "in": ["agency", "receipts"]}}
        st["bookings_confirmed"]["model"] = {"flatAmount": {"lower": 1}, "travelMethod": {"in": ["agency"]}}
        rep = B.validate(b, meta())
        self.assertEqual(rep.errors, [])
        pw = "workflows.Invitation.states.bookings_confirmed.model"
        self.assertIn(f"{pw}.flatAmount: 'flatAmount' cannot be set in bookings but bookings_confirmed requires it (`confirm_bookings`): require it before bookings or let bookings change it", rep.warnings)
        self.assertIn(f"{pw}.travelMethod: 'travelMethod' cannot be changed in bookings but bookings_confirmed allows only agency (`confirm_bookings`)", rep.warnings)
        st["bookings"]["model"] = {"flatAmount": {"lower": 1, "readonly": True}, "travelMethod": {"readonly": True, "in": ["agency"]}}   # settled before: fine
        self.assertEqual([w for w in B.validate(b, meta()).warnings if "bookings_confirmed" in w], [])
        # a dead transition: the source only allows values the target refuses, whether or not the source is read only
        st["bookings"]["model"] = {"travelMethod": {"in": ["receipts", "flat"]}}
        st["bookings_confirmed"]["model"] = {"travelMethod": {"in": ["agency"]}}
        rep = B.validate(b, meta())
        self.assertEqual(sorted(rep.errors), [   # both ways: `rebook` goes back to bookings
            "workflows.Invitation.states.bookings.model.travelMethod: 'travelMethod' is agency in bookings_confirmed but bookings allows only receipts, flat: `rebook` can never fire",
            f"{pw}.travelMethod: 'travelMethod' is receipts, flat in bookings but bookings_confirmed allows only agency: `confirm_bookings` can never fire"])
        self.assertEqual([w for w in rep.warnings if "confirm_bookings" in w], [])
        st["bookings"]["model"] = {"travelMethod": {"in": ["receipts", "agency"]}}   # a value in common: the record sets it in bookings, fine
        self.assertEqual([x for x in B.validate(b, meta()).errors + B.validate(b, meta()).warnings if "confirm_bookings" in x], [])
        m = meta()                                                         # optional in both states: null is a value in common
        m["classes"]["Invitation"]["attributes"]["travelMethod"] = {"type": "TravelMethod"}
        st["bookings"]["model"] = {"travelMethod": {"in": ["receipts"]}}
        self.assertEqual([x for x in B.validate(b, m).errors if "confirm_bookings" in x], [])
        st["bookings_confirmed"]["model"] = {"travelMethod": {"lower": 1, "in": ["agency"]}}
        self.assertEqual(len([x for x in B.validate(b, m).errors if "can never fire" in x]), 2)   # confirm_bookings and rebook

    def test_view_as_who_may_use_the_app_as_another_user(self):
        b = behavior()
        b["view_as"] = {"users_by": ["admin", "office"]}
        rep = B.validate(b, meta())
        self.assertEqual(rep.errors, [])
        self.assertEqual([w for w in rep.warnings if "view_as" in w], [])
        x = B.expand(b)
        self.assertEqual(x["view_as"], {"users_by": ["admin", "office"]})
        self.assertIsNone(B.expand(behavior())["view_as"])
        md = B.to_markdown(b, meta(), "en")
        self.assertIn("**View as**: anyone may restrict their session to one of their roles; `admin`, `office` may use the application as another user", md)
        self.assertNotIn("View as", B.to_markdown(behavior(), meta(), "en"))
        # the file keeps it on one line after roles; an empty mapping stays (roles only)
        text = B.dumps(b)
        self.assertIn("\nview_as: {users_by: [admin, office]}\n", text)
        self.assertEqual(B.expand(B.loads(text))["view_as"], {"users_by": ["admin", "office"]})
        self.assertIn("view_as: {}", B.dumps({**b, "view_as": {"users_by": []}}))
        self.assertEqual(B.expand(B.from_editor(B.runtime_json(b, meta())))["view_as"], {"users_by": ["admin", "office"]})
        # diff
        self.assertEqual(B.diff(behavior(), b), ["+ view_as (users_by: admin, office)"])
        self.assertEqual(B.diff(b, {**b, "view_as": {"users_by": ["admin"]}}), ["~ view_as: users_by admin"])
        self.assertEqual(B.diff(b, behavior()), ["- view_as"])
        # what validate refuses: scoped roles, record paths, unknown roles and keys; an empty list is a warning
        bad = behavior()
        bad["view_as"] = {"users_by": ["director", "self.issuer", "creator", "boss", "admin", "admin"], "x": 1}
        rep = B.validate(bad, meta())
        for expected in ("view_as: unknown keys: x (allowed: doc, users_by)",
                         "view_as.users_by: 'director' is held per Department: acting as another user needs a role without scope",
                         "view_as.users_by: 'self.issuer': only admin or a role declared in roles without scope (who may act as another user is not a property of a record)",
                         "view_as.users_by: 'creator': only admin or a role declared in roles without scope (who may act as another user is not a property of a record)",
                         "view_as.users_by: unknown role 'boss'",
                         "view_as.users_by: 'admin' listed twice"):
            self.assertIn(expected, rep.errors)
        bad["view_as"] = "admin"
        self.assertIn("view_as: a mapping: {users_by: [admin, <role>]}", B.validate(bad, meta()).errors)
        bad["view_as"] = {}
        rep = B.validate(bad, meta())
        self.assertEqual(rep.errors, [])
        self.assertIn("view_as: users_by is empty: nobody acts as another user; the session can still be restricted to one of the user's roles", rep.warnings)

    def test_domain_md_follows_the_state_model(self):
        import argparse
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "domain.ecore.yaml").write_text(META.read_text())
            (root / "behavior.yaml").write_text(BEHAVIOR.read_text())
            cli.sync(root)
            self.assertNotIn("1 from", (root / "docs/DOMAIN.md").read_text())
            self.assertEqual(cli.docs_status(root)["state"], "aligned")
            text = BEHAVIOR.read_text().replace("pending_director:      {label", "pending_director:      {requires: [hours], model: {flatAmount: {readonly: true}}, label", 1)
            (root / "behavior.yaml").write_text(text)
            self.assertEqual(cli.docs_status(root)["state"], "stale")             # the overlay changed: regenerate
            cli.sync(root)
            dm = (root / "docs/DOMAIN.md").read_text()
            self.assertIn("| hours | EBigDecimal | 0..1 · 1 from Awaiting approval |  |  |", dm)
            self.assertIn("| flatAmount | EBigDecimal | 0..1 | read only from Awaiting approval |  |", dm)
            self.assertEqual(cli.docs_status(root)["state"], "aligned")
            # the metamodel as seen from the state, from the command line
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(cli.cmd_show(argparse.Namespace(path=str(root), format="emfatic", state="Invitation.pending_director", behavior=None)), 0)
            self.assertIn("  attr EBigDecimal[1] hours;", out.getvalue())
            self.assertIn("  readonly attr EBigDecimal flatAmount;", out.getvalue())
            err = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                self.assertEqual(cli.cmd_show(argparse.Namespace(path=str(root), format="emfatic", state="Invitation.nope", behavior=None)), 1)
            self.assertIn("Invitation.pending_director", err.getvalue())
            # a broken behaviour: DOMAIN.md is the metamodel's alone
            (root / "behavior.yaml").write_text(text.replace("guard: dataComplete,", "guard: nope,", 1))
            cli.sync(root)
            self.assertNotIn("1 from", (root / "docs/DOMAIN.md").read_text())
            self.assertEqual(cli.docs_status(root)["state"], "aligned")

    def test_workflow_rules(self):
        b = behavior()
        w = b["workflows"]["Invitation"]
        w["transitions"]["approve"]["to"] = "nowhere"
        w["transitions"]["submit"]["from"] = []
        w["transitions"]["reject"]["comment"] = "maybe"
        w["transitions"]["close"]["emits"] = ["paid"]
        w["transitions"]["visit_ended"]["at"] = "notes + 1d"
        w["transitions"]["cancel"]["guard"] = "hours"
        w["transitions"]["rebook"]["when"] = "transition = rebook"
        w["transitions"]["resubmit"].pop("by")
        w["states"]["closed"]["reminder"] = {"after": "3 days"}
        w["states"]["lost"] = {}
        errs = errors(b)
        for frag in ["approve: to: unknown state 'nowhere'", "submit: from: one or more states", "reject.comment: required or optional",
                     "close.emits: 'paid' is not declared in events.Invitation (visit_ended)",
                     "visit_ended.at: 'notes' is text: a Date or DateTime attribute",
                     "cancel.guard: expected bool, found number", "rebook.when: 'transition' is not a feature",
                     "resubmit: who performs it", "closed.reminder: after: a duration", "states.lost: unreachable"]:
            self.assertTrue(any(frag in x for x in errs), (frag, errs))
        b = behavior()
        b["workflows"]["Invitation"]["state"] = "code"
        b["workflows"]["Invitation"]["states"].pop("closed")
        b["workflows"]["Invitation"]["states"]["cancelled"]["initial"] = True
        b["workflows"]["Invitation"]["revert"] = {"comment": "required"}
        errs = errors(b)
        for frag in ["is initial or final, not both", "revert: by: who can bring", "exactly one state is `initial: true` (found 2)"]:
            self.assertTrue(any(frag in x for x in errs), (frag, errs))
        self.assertTrue(any("transitions.close: to: unknown state 'closed'" in x for x in errs), errs)
        b = behavior()
        b["workflows"]["Invitation"]["state"] = "hours"
        self.assertTrue(any("'hours' is EBigDecimal: the state attribute is an EString or an enum" in x for x in errors(b)))
        b = behavior()
        b["workflows"]["Department"] = {"state": "name", "states": {"a": {"initial": True}, "b": {"final": True}},
                                        "transitions": {"go": {"from": "a", "to": "b", "by": ["office"]}}}
        self.assertEqual(errors(b), [])
        b["workflows"]["Nope"] = b["workflows"].pop("Department")
        self.assertIn("workflows.Nope: unknown class Nope", errors(b))

    def test_state_attribute_as_an_enum(self):
        m = meta()
        m["enums"]["InvitationState"] = ["draft", "pending_director", "rejected", "bookings", "bookings_confirmed", "in_management",
                                         "awaiting_confirmation", "director_confirmation", "payment", "closed", "cancelled"]
        m["classes"]["Invitation"]["attributes"]["state"] = {"type": "InvitationState", "lower": 1}
        self.assertEqual(errors(behavior(), m), [])
        m["enums"]["InvitationState"] = ["draft", "closed", "cancelled", "archived"]
        errs = errors(behavior(), m)
        self.assertTrue(any("states: not literals of InvitationState: pending_director, rejected" in x for x in errs), errs)
        self.assertTrue(any("literals of InvitationState without a state: archived" in x for x in errs), errs)

    def test_principals(self):
        b = behavior()
        w = b["workflows"]["Invitation"]
        w["states"]["draft"]["owner"] = ["issuer"]                     # the role, not the reference
        w["states"]["pending_director"]["owner"] = ["boss"]
        w["states"]["bookings"]["owner"] = ["office@department"]
        w["states"]["payment"]["owner"] = ["self.guest"]
        w["states"]["rejected"]["editable_by"] = ["self"]
        w["transitions"]["approve"]["by"] = ["director@guest"]
        w["transitions"]["close"]["by"] = ["self.department.createdBy", "admin", "creator"]
        b["reactions"][0]["notify"] = ["self.guest"]
        b["reactions"][1]["notify"] = ["self.invitationFunds.createdBy", "self.department.createdBy.email"]
        errs = errors(b)
        self.assertTrue(any("draft.owner: role issuer is held per Department" in x for x in errs) is False)   # issuer resolves via department
        for frag in ["pending_director.owner: unknown role 'boss'", "bookings.owner: role office has no scope: write it without @department",
                     "payment.owner: 'self.guest' is Guest: a principal path leads to a User reference",
                     "rejected.editable_by: 'self' is the record", "approve.by: 'director@guest': guest is Guest, the scope of director is Department",
                     "notify_submitted.notify: 'self.guest' is Guest: a principal path leads to a User reference or an Email attribute"]:
            self.assertTrue(any(frag in x for x in errs), (frag, errs))
        self.assertFalse(any("close.by" in x or "notify_to_manage" in x for x in errs), errs)
        # a role scoped by a class the record does not reference, or references twice
        b = behavior()
        b["reactions"].append({"name": "hello", "event": "Guest.created", "notify": ["director"], "template": "guest_created"})
        self.assertTrue(any("hello.notify: role director is held per Department, and Guest has no reference to Department" in x
                            for x in errors(b)))
        m = meta()
        m["classes"]["Invitation"]["references"]["payer"] = "Department"
        errs = errors(behavior(), m)
        self.assertTrue(any("several references to it (department, payer): write director@department" in x for x in errs), errs)
        b = behavior()
        b["workflows"]["Invitation"]["states"]["pending_director"]["owner"] = ["director@department"]
        self.assertFalse(any("pending_director.owner" in x for x in errors(b, m)))
        # a reference with the same name as a role: say how to write each
        b = behavior()
        b["roles"].pop("issuer")
        b["workflows"]["Invitation"]["states"]["draft"]["owner"] = ["issuer"]
        self.assertTrue(any("unknown role 'issuer' (the reference Invitation.issuer: write self.issuer)" in x for x in errors(b)))

    def test_roles_events_reactions_subscriptions(self):
        b = behavior()
        b["roles"]["admin"] = {}
        b["roles"]["Boss"] = {"scope": "Nope"}
        b["roles"]["clerk"] = {"scope": "User", "colour": "red"}
        b["events"]["Invitation"]["created"] = {}
        b["events"]["Invitation"]["Visit-ended"] = {}
        b["events"]["Nope"] = {"x": {}}
        b["reactions"][0]["event"] = "Invitation.paid"
        b["reactions"][1]["event"] = "Nope.created"
        b["reactions"][2]["event"] = "Invitation"
        b["reactions"][3]["name"] = b["reactions"][4]["name"]
        b["reactions"][5].pop("template")
        b["reactions"][6]["notify"] = []
        b["reactions"][7]["extra"] = 1
        b["reactions"][8]["when"] = "transition = nope"
        b["subscriptions"][0]["events"] = ["Invitation.paid", "Nope.*", "bad", "Guest.created", "user.*", "webhook.test"]
        b["subscriptions"].append({"name": "n8n", "url_env": "lower", "events": []})
        b["subscriptions"].append({"name": "slack", "events": ["Invitation.*"]})
        errs = errors(b)
        for frag in ["roles.admin: 'admin' is built in", "roles.Boss: role names are lowercase", "roles.Boss: scope: unknown class Nope",
                     "roles.clerk: scope User: a role is held per instance of a domain class", "roles.clerk: unknown keys: colour",
                     "events.Invitation.created: 'created' is a built-in event", "events.Invitation.Visit-ended: event names are lowercase",
                     "events.Nope: unknown class Nope", "notify_submitted: event: Invitation has no event 'paid' (created, updated, deleted, "
                     "transitioned, completed, reverted, reminder, visit_ended", "notify_to_manage: event: unknown class Nope",
                     "notify_to_book: event: <Class>.<event>", "reaction 'notify_rejected' declared twice",
                     "notify_bookings_guest: template: the key", "notify_bookings_issuer: notify: who is notified",
                     "notify_rebook: unknown keys: extra", "notify_visit_ended.when: 'nope' is not a literal of one of the names",
                     "subscriptions[0] n8n.events: 'Invitation.paid': Invitation has no event 'paid'", "'Nope.*': unknown class Nope",
                     "'bad': <Class>.<event> or <Class>.*", "subscription 'n8n' declared twice", "url_env 'lower': an environment variable name",
                     "subscriptions[1] n8n: events: patterns", "subscriptions[2] slack: url_env"]:
            self.assertTrue(any(frag in x for x in errs), (frag, errs))
        self.assertFalse(any("'Guest.created'" in x or "'user.*'" in x or "'webhook.test'" in x for x in errs), errs)

    def test_derivations(self):
        b = behavior()
        d = b["derivations"]["Invitation"]
        d["notes"] = "hours > 1"                                    # not derived in the metamodel
        d["fundsTotal"] = "reason.isSet()"                          # wrong type
        d["agencyBookingRequired"] = "travelMethod = agency or hours.nope()"
        d["nope"] = "true"
        b["derivations"]["Nope"] = {"x": "true"}
        errs = errors(b)
        for frag in ["derivations.Invitation.notes: Invitation.notes is not derived: mark it `derived: true`",
                     "derivations.Invitation.fundsTotal: expected number, found bool",
                     "derivations.Invitation.agencyBookingRequired: unknown operation nope()",
                     "derivations.Invitation.nope: 'nope' is not an attribute of Invitation", "derivations.Nope: unknown class Nope"]:
            self.assertTrue(any(frag in x for x in errs), (frag, errs))
        b = behavior()
        d = b["derivations"]["Invitation"]
        d["agencyBookingRequired"] = "accommodationBookingComplete"
        d["accommodationBookingComplete"] = "travelBookingComplete"
        d["travelBookingComplete"] = "not agencyBookingRequired"
        errs = errors(b)
        self.assertTrue(any("derivations depend on each other: agencyBookingRequired -> accommodationBookingComplete -> "
                            "travelBookingComplete -> agencyBookingRequired" in x for x in errs), errs)
        self.assertEqual(B._cycle({"a": {"b"}, "b": {"c"}, "c": set()}), None)
        self.assertEqual(B._cycle({"a": {"a"}}), ["a", "a"])
        m = meta()
        m["classes"]["Invitation"]["attributes"]["dataComplete"] = "EBoolean"
        self.assertTrue(any("dataComplete: Invitation.dataComplete is not derived" in x for x in errors(behavior(), m)))

    def test_top_level_and_shapes(self):
        b = behavior()
        b["workflow"] = b.pop("workflows")
        errs = errors(b)
        self.assertTrue(any("unknown top-level keys: workflow" in x for x in errs), errs)
        self.assertTrue(any("notify_submitted: event: Invitation has no event 'transitioned'" in x for x in errs), errs)
        self.assertEqual(errors({}), [])                            # an empty behaviour is fine
        with self.assertRaises(M.ModelError):
            B.loads("- just a list\n")


class DerivedInTheMetamodelTests(unittest.TestCase):
    def test_derived_attribute(self):
        m = meta()
        rep = E.validate(m)
        self.assertEqual(rep.errors, [])
        self.assertIn("derived attr EBoolean dataComplete;", E.to_emfatic(m))
        self.assertNotIn("readonly derived", E.to_emfatic(m))
        md = E.to_markdown(m, "en")
        self.assertIn("| dataComplete | EBoolean | 0..1 | derived |", md)
        self.assertIn("calcolato", E.to_markdown(m, "it"))
        back = E.import_ecore(E.export_ecore(m))
        self.assertTrue(back["classes"]["Invitation"]["attributes"]["dataComplete"]["derived"])
        self.assertIn('derived="true"', E.export_ecore(m))
        plain = copy.deepcopy(m)
        plain["classes"]["Invitation"]["attributes"]["dataComplete"] = "EBoolean"
        self.assertIn("~ Invitation.dataComplete: derived None -> True", E.diff(plain, m))
        bad = copy.deepcopy(m)
        bad["classes"]["Invitation"]["attributes"]["code"].update({"derived": True, "id": True})
        bad["classes"]["Invitation"]["attributes"]["dataComplete"]["changeable"] = True
        errs = E.validate(bad).errors
        self.assertTrue(any("code: a derived attribute cannot be the id" in x for x in errs), errs)
        self.assertTrue(any("dataComplete: a derived attribute is read only" in x for x in errs), errs)
        bad = copy.deepcopy(m)
        bad["workflows"] = {}
        self.assertTrue(any("live in behavior.yaml" in x for x in E.validate(bad).errors))


class CliAndHookTests(unittest.TestCase):
    HOOK = ROOT / "hooks" / "hook.py"

    def run_cli(self, *args):
        import contextlib
        import io
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def run_hook(self, payload):
        return subprocess.run([sys.executable, str(self.HOOK), "post"], input=json.dumps(payload), capture_output=True, text=True)

    def test_validate_checks_the_behaviour_next_to_the_metamodel(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "domain.ecore.yaml").write_text(META.read_text())
            code, out, _ = self.run_cli("validate", str(root / "domain.ecore.yaml"))
            self.assertEqual(code, 0)
            self.assertNotIn("behavior.yaml", out)
            (root / "behavior.yaml").write_text(BEHAVIOR.read_text().replace("    fundsTotal: invitationFunds.amount.sum()\n", ""))
            code, out, _ = self.run_cli("validate", str(root / "domain.ecore.yaml"))
            self.assertEqual(code, 0)
            self.assertIn("--- behavior.yaml against the metamodel", out)
            self.assertIn("WARNING derivations.Invitation.fundsTotal", out)
            code, out, _ = self.run_cli("validate", str(root / "domain.ecore.yaml"), "--json")
            data = json.loads(out)
            self.assertTrue(data["ok"] and data["behavior"]["ok"])
            self.assertEqual(len(data["behavior"]["warnings"]), 1)
            (root / "behavior.yaml").write_text(BEHAVIOR.read_text())
            code, out, _ = self.run_cli("validate", str(root / "domain.ecore.yaml"))
            self.assertIn("Behaviour OK", out)
            text = (root / "domain.ecore.yaml").read_text().replace("      endDate: {type: Date, lower: 1}\n", "      visitEnd: {type: Date, lower: 1}\n")
            (root / "domain.ecore.yaml").write_text(text)
            code, out, _ = self.run_cli("validate", str(root / "domain.ecore.yaml"))
            self.assertEqual(code, 1)
            self.assertIn("Metamodel OK", out)
            self.assertIn("visit_ended.at: 'endDate' is not a feature of Invitation", out)
            code, out, _ = self.run_cli("validate", str(root / "domain.ecore.yaml"), "--json")
            self.assertFalse(json.loads(out)["ok"])
            (root / "domain.ecore.yaml").write_text("package: x\nclasses:\n  A:\n    attributes: {x: Strin}\n")
            code, out, _ = self.run_cli("validate", str(root / "domain.ecore.yaml"))
            self.assertEqual(code, 1)
            self.assertIn("behavior.yaml: not checked (the metamodel must be valid first)", out)
            code, out, _ = self.run_cli("validate", str(META), "--behavior", str(root / "behavior.yaml"))
            self.assertEqual(code, 0)

    def test_apply_reports_a_proposal_that_breaks_the_behaviour(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "domain.ecore.yaml").write_text(META.read_text())
            (root / "behavior.yaml").write_text(BEHAVIOR.read_text())
            new = meta()
            new["classes"]["Invitation"]["attributes"]["visitEnd"] = new["classes"]["Invitation"]["attributes"].pop("endDate")
            (root / "p.json").write_text(json.dumps(new))
            code, out, _ = self.run_cli("apply", str(root / "p.json"), "--path", str(root / "domain.ecore.yaml"))
            self.assertEqual(code, 0)
            self.assertIn("The proposal breaks behavior.yaml (fix the behaviour in the same change):", out)
            self.assertIn("visit_ended.at: 'endDate' is not a feature", out)
            self.assertIn("dry run", out)

    def test_hook_checks_both_files(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            meta_f, beh_f = root / "domain.ecore.yaml", root / "behavior.yaml"
            meta_f.write_text(META.read_text())
            beh_f.write_text(BEHAVIOR.read_text())
            out = self.run_hook({"tool_input": {"file_path": str(beh_f)}})
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn("behaviour valid against the metamodel", out.stdout)
            self.assertNotIn("WARNING", out.stdout)
            beh_f.write_text(BEHAVIOR.read_text().replace("    fundsTotal: invitationFunds.amount.sum()\n", ""))
            out = self.run_hook({"tool_input": {"file_path": str(beh_f)}})
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn("WARNING derivations.Invitation.fundsTotal", out.stdout)
            beh_f.write_text(BEHAVIOR.read_text().replace("guard: dataComplete,", "guard: dataComplet,", 1))
            out = self.run_hook({"tool_input": {"file_path": str(beh_f)}})
            self.assertEqual(out.returncode, 2)
            self.assertIn("behavior.yaml is not valid against domain.ecore.yaml", out.stderr)
            self.assertIn("'dataComplet' is not a feature of Invitation", out.stderr)
            beh_f.write_text(BEHAVIOR.read_text())
            # the domain changes under the behaviour
            meta_f.write_text(META.read_text().replace("      endDate: {type: Date, lower: 1}\n", "      visitEnd: {type: Date, lower: 1}\n"))
            out = self.run_hook({"tool_input": {"file_path": str(meta_f)}})
            self.assertEqual(out.returncode, 2)
            self.assertIn("this change of domain.ecore.yaml breaks behavior.yaml", out.stderr)
            self.assertIn("visit_ended.at", out.stderr)
            meta_f.write_text(META.read_text())
            out = self.run_hook({"tool_input": {"file_path": str(meta_f)}})
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn("metamodel valid", out.stdout)
            beh_f.write_text("- not a mapping\n")
            out = self.run_hook({"tool_input": {"file_path": str(beh_f)}})
            self.assertEqual(out.returncode, 2)
            self.assertIn("behavior.yaml: the metamodel must be a mapping", out.stderr)
            # a behavior.yaml without a metamodel next to it is none of our business
            lone = root / "elsewhere"
            lone.mkdir()
            (lone / "behavior.yaml").write_text("roles: {}\n")
            self.assertEqual(self.run_hook({"tool_input": {"file_path": str(lone / "behavior.yaml")}}).returncode, 0)

    def test_session_mentions_the_behaviour_model(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "domain.ecore.yaml").write_text(META.read_text())
            out = subprocess.run([sys.executable, str(self.HOOK), "session"], input=json.dumps({"cwd": d}), capture_output=True, text=True)
            self.assertNotIn("Behaviour model", out.stdout)
            (root / "behavior.yaml").write_text(BEHAVIOR.read_text())
            out = subprocess.run([sys.executable, str(self.HOOK), "session"], input=json.dumps({"cwd": d}), capture_output=True, text=True)
            self.assertIn("Behaviour model", out.stdout)


if __name__ == "__main__":
    unittest.main()


class ArithmeticAndSqlTests(unittest.TestCase):
    def setUp(self):
        self.e = E.expand(meta())
        self.ctx = X.Context(self.e, "Invitation")

    def sql(self, text, cls="Invitation", e=None, **kw):
        e = e or self.e
        node, _ = X.check(text, X.Context(e, cls, **kw))
        return X.to_sql(node, X.SqlContext(e, cls, variables={"transition": "(p_extra -> 'transition' ->> 'key')"}))

    def test_arithmetic_functions_and_if(self):
        c = lambda t: X.check(t, self.ctx)[1]  # noqa: E731
        self.assertEqual(c("hours * hourlyRate + 1"), "number")
        self.assertEqual(c("invitationFunds.size() + 1"), "int")
        self.assertEqual(c("invitationFunds.size() / 2"), "number")
        self.assertEqual(c("endDate - startDate"), "int")
        self.assertEqual(c("round(hours * hourlyRate, 2)"), "number")
        self.assertEqual(c("coalesce(flatAmount, 0)"), "number")
        self.assertEqual(c("coalesce(notes, 'x')"), "text")
        self.assertEqual(c("if compensationType = hourly then hours else 0"), "number")
        self.assertEqual(c("if dataComplete then reason.code else 'n/a'"), "string")
        self.assertEqual(c("-hours"), "number")
        self.assertEqual(X.to_text(X.parse("if a then 1 else 2 + 3")), "if a then 1 else 2 + 3")
        self.assertEqual(X.to_text(X.parse("(if a then 1 else 2) + 3")), "(if a then 1 else 2) + 3")
        self.assertEqual(X.to_text(X.parse("not (a = 1 or b)")), "not (a = 1 or b)")
        self.assertEqual(X.to_text(X.parse("a - (b - c)")), "a - (b - c)")
        self.assertEqual(X.to_text(X.parse("(a - b) - c")), "a - b - c")
        self.assertEqual(X.to_text(X.parse("(a + b) * c")), "(a + b) * c")
        for text, frag in [("hours + 'a'", "'+' needs numbers"), ("startDate - 1", "'-' needs numbers, found date and int"),
                           ("round(hours, 1.5)", "optional integer number of decimals"), ("round()", "expected"),
                           ("round(1, 2, 3)", "round() takes 1 to 2 argument(s), found 3"), ("coalesce(hours)", "coalesce() takes at least 2"),
                           ("if hours then 1 else 2", "'if' needs a boolean condition"), ("if dataComplete then 1 else 'a'", "'then' gives int, 'else' gives string"),
                           ("coalesce(hours, 'x')", "coalesce() mixes number and string"), ("-notes", "'-' needs a number"),
                           ("if dataComplete then 1", "expected 'else'"), ("invitationFunds + 1", "'+' cannot take a collection"),
                           ("reason + 1", "'+' cannot take a reference"), ("coalesce(reason, guest)", "coalesce() cannot take a reference")]:
            with self.assertRaises(X.ExprError, msg=text) as cm:
                X.check(text, self.ctx)
            self.assertIn(frag, str(cm.exception), text)

    def test_sql_of_paths(self):
        self.assertEqual(self.sql("dataComplete"), "r.data_complete")
        self.assertEqual(self.sql("reason.code = 'x'"),
                         "(select x1.code from public.invitation_reasons x1 where x1.id = r.reason) = 'x'")
        self.assertEqual(self.sql("department.createdBy.email"),
                         "(select x2.email from public.departments x1 join public.profiles x2 on x2.id = x1.created_by where x1.id = r.department)")
        self.assertEqual(self.sql("invitationFunds.amount.sum()"),
                         "(select coalesce(sum(x1.amount), 0) from public.invitation_funds x1 where x1.invitation = r.id)")
        self.assertEqual(self.sql("invitationFunds.size()"), "(select count(*) from public.invitation_funds x1 where x1.invitation = r.id)")
        self.assertEqual(self.sql("invitationFunds.notEmpty()"), "exists (select 1 from public.invitation_funds x1 where x1.invitation = r.id)")
        self.assertEqual(self.sql("invitationFunds.isEmpty()"), "not exists (select 1 from public.invitation_funds x1 where x1.invitation = r.id)")
        self.assertEqual(self.sql("reason.isSet()"), "r.reason is not null")
        self.assertEqual(self.sql("reason.isEmpty()"), "not (r.reason is not null)")
        self.assertEqual(self.sql("accommodationVenue.isSet()"), "nullif(trim(r.accommodation_venue), '') is not null")
        self.assertEqual(self.sql("hours.isSet()"), "r.hours is not null")
        self.assertEqual(self.sql("reason.economicRates.size()"),
                         "(select count(*) from public.invitation_reasons x1 join public.economic_rates x2 on x2.reason = x1.id where x1.id = r.reason)")
        self.assertEqual(self.sql("compensationType in [hourly, flat]"), "r.compensation_type in ('hourly', 'flat')")
        self.assertEqual(self.sql("not agencyBookingRequired and hours > 0"), "(not (r.agency_booking_required) and r.hours > 0)")
        self.assertEqual(self.sql("mealsAmount / (endDate - startDate + 1)"), "(r.meals_amount::numeric / ((r.end_date - r.start_date) + 1))")
        self.assertEqual(self.sql("round(hours * hourlyRate, 2)"), "round(((r.hours * r.hourly_rate))::numeric, 2)")
        self.assertEqual(self.sql("if compensationType = flat then coalesce(flatAmount, 0) else 0"),
                         "case when r.compensation_type = 'flat' then coalesce(r.flat_amount, 0) else 0 end")
        self.assertEqual(self.sql("state = 'it''s'".replace("''", "\\'")), "r.state = 'it''s'")
        self.assertEqual(self.sql("transition = submit", variables={"transition": X.ENUM + "@transition"}, names={"@transition": ["submit"]}),
                         "(p_extra -> 'transition' ->> 'key') = 'submit'")
        # join tables and containment without opposite (anagrafica: Italian table names)
        e2 = E.expand(E.load(FIXTURES / "anagrafica.ecore.yaml"))
        self.assertEqual(self.sql("gruppi.nome", "Persona", e2),
                         "(select x2.nome from public.persone_gruppi x1 join public.gruppi x2 on x2.id = x1.gruppo_id where x1.persona_id = r.id)")
        self.assertEqual(self.sql("membri.size()", "Gruppo", e2),
                         "(select count(*) from public.persone_gruppi x1 join public.persone x2 on x2.id = x1.persona_id where x1.gruppo_id = r.id)")
        self.assertEqual(self.sql("allegati.notEmpty()", "Gruppo", e2), "exists (select 1 from public.allegati x1 where x1.gruppo = r.id)")
        self.assertEqual(self.sql("indirizzi.size() > 0", "Persona", e2), "(select count(*) from public.indirizzi x1 where x1.persona = r.id) > 0")
        # one-to-one: the foreign key sits on the mandatory side (Persona.account is [1]), so Account navigates it inversely
        self.assertEqual(self.sql("account.email", "Persona", e2), "(select x1.email from public.account x1 where x1.id = r.account)")
        self.assertEqual(self.sql("account.isSet()", "Persona", e2), "r.account is not null")
        self.assertEqual(self.sql("persona.isSet()", "Account", e2), "exists (select 1 from public.persone x1 where x1.account = r.id)")
        self.assertEqual(self.sql("persona.codiceFiscale", "Account", e2), "(select x1.codice_fiscale from public.persone x1 where x1.account = r.id)")
        self.assertEqual(self.sql("persona.nome", "Indirizzo", e2), "(select x1.nome from public.persone x1 where x1.id = r.persona)")
        self.assertEqual(self.sql("utente.email", "Persona", e2), "(select x1.email from public.profiles x1 where x1.id = r.utente)")
        with self.assertRaises(X.ExprError):
            self.sql("reason")                    # a reference has no scalar SQL


class GenerationTests(unittest.TestCase):
    def test_markdown(self):
        md = B.to_markdown(behavior(), meta())
        self.assertTrue(md.startswith("# Behaviour of the domain invitations\n"))
        for frag in ["## Roles", "| director | Department director | per Department |", "## Workflow of Invitation",
                     "The state is the attribute `state`.", "```mermaid\nstateDiagram-v2\n  draft: Draft", "  [*] --> draft", "  closed --> [*]",
                     "  in_management --> awaiting_confirmation: Visit ended (auto)", "  draft --> cancelled: Cancel",
                     "| `awaiting_confirmation` | Awaiting visit confirmation |  | `self.issuer` | `self.issuer`, `office` |  | after 7d (`visit_confirmation_reminder`) |",
                     "| `approve` | Approve | pending_director → in_management | `director` | `not agencyBookingRequired` | `dataComplete` |  |  | `office` (`invitation_to_manage`); `self.issuer` (`invitation_approved`) |",
                     "| `submit` | Submit | draft → pending_director | `self.issuer` |  | `dataComplete` |  |  | `director` (`invitation_submitted`) |",
                     "| `visit_ended` | Visit ended | in_management → awaiting_confirmation | system: `endDate + 1d` |  |  |  | `visit_ended` |",
                     "| `withdraw` | Cancel | draft, rejected → cancelled | `self.issuer`, `office` |", "| `reject` | Reject | pending_director → rejected | `director` |  |  | required |  |",
                     "Back to a previous state: `office`, `director`; from a final state: `office`; comment required.",
                     "## Derived attributes", "| Invitation | `fundsTotal` | `invitationFunds.amount.sum()` |",
                     "## Classes involved in the behaviour", "| Guest | `email` | notify: `notify_bookings_guest` |",
                     "| Department | — | scope: `issuer`, scope: `director` |",
                     "## Events", "| Invitation | `visit_ended` | La visita è terminata (passaggio automatico alla data di fine) |",
                     "## Reactions", "| `notify_bookings_guest` | `Invitation.transitioned` | `transition = confirm_bookings` | `self.guest.email` | `bookings_confirmed_guest` |",
                     "| `notify_reverted` | `Invitation.reverted` |  | `self.issuer` | `invitation_reverted` |",
                     "## Subscriptions", "| `n8n` | `$N8N_WEBHOOK_URL` | `Invitation.*`, `Guest.*`, `user.*` |"]:
            self.assertIn(frag, md)
        it = B.to_markdown(behavior(), meta(), "it")
        self.assertIn("# Comportamento del dominio invitations", it)
        self.assertIn("| `draft` | Bozza | iniziale |", it)
        self.assertIn("sistema: `endDate + 1d`", it)
        self.assertIn("## Classi coinvolte nel comportamento", it)
        self.assertEqual(B.to_markdown(behavior(), meta()), md)                         # deterministic
        self.assertTrue(B.markdown_document(behavior(), meta()).startswith(B.MARKDOWN_MARK + "\n# "))
        m = meta()
        m["classes"]["Invitation"]["attributes"]["extra"] = {"type": "EInt", "derived": True}
        self.assertIn("| Invitation | `extra` | *computed in code* |", B.to_markdown(behavior(), m))
        self.assertIn("*calcolato nel codice*", B.to_markdown(behavior(), m, "it"))

    def test_uses(self):
        u = B.runtime_json(behavior(), meta())["uses"]
        # derivations navigate into other classes: their features are involved too
        self.assertIn({"kind": "derivation", "of": "Invitation.compensationType"}, u["InvitationReason"]["attributes"]["compensationType"])
        self.assertIn({"kind": "derivation", "of": "Invitation.fundsTotal"}, u["InvitationFund"]["attributes"]["amount"])
        self.assertIn({"kind": "derivation", "of": "Invitation.fundsTotal"}, u["Invitation"]["references"]["invitationFunds"])
        inv = u["Invitation"]
        self.assertIn({"kind": "guard", "of": "Invitation.submit"}, inv["attributes"]["dataComplete"])
        self.assertIn({"kind": "when", "of": "Invitation.approve"}, inv["attributes"]["agencyBookingRequired"])
        self.assertIn({"kind": "at", "of": "Invitation.visit_ended"}, inv["attributes"]["endDate"])
        # principals: self.<reference>, roles held per scope (through the reference that leads to the scope), recipients
        self.assertIn({"kind": "owner", "of": "Invitation.draft"}, inv["references"]["issuer"])
        self.assertIn({"kind": "by", "of": "Invitation.submit"}, inv["references"]["issuer"])
        self.assertIn({"kind": "notify", "of": "notify_approved"}, inv["references"]["issuer"])
        self.assertIn({"kind": "by", "of": "Invitation.approve"}, inv["references"]["department"])
        self.assertIn({"kind": "revert", "of": "Invitation"}, inv["references"]["department"])
        self.assertIn({"kind": "notify", "of": "notify_bookings_guest"}, inv["references"]["guest"])
        self.assertEqual(u["Guest"]["attributes"]["email"], [{"kind": "notify", "of": "notify_bookings_guest"}])
        self.assertEqual(u["Department"]["class"], [{"kind": "scope", "of": "issuer"}, {"kind": "scope", "of": "director"}])
        for cname in ("Fund", "Position", "EconomicRate"):                       # purely structural classes
            self.assertNotIn(cname, u)
        self.assertNotIn("@transition", str(u))                                  # the variable of a reaction is not a feature
        self.assertEqual(json.loads(json.dumps(u)), u)
        # a derivation that does not type-check contributes nothing (validate reports it)
        b = behavior()
        b["derivations"]["Invitation"]["fundsTotal"] = "nope.sum()"
        self.assertNotIn("fundsTotal", str(B.uses(B.expand(b), E.expand(meta()))["Invitation"]["references"].get("invitationFunds", [])))

    def test_dumps_from_editor_and_diff(self):
        # dumps writes behavior.yaml back: same model once loaded
        text = B.dumps(behavior())
        self.assertTrue(text.startswith("# Behaviour of the domain (behavior.yaml)"))
        self.assertIn("\ndoc: Inviti dei visiting researcher", text)
        self.assertIn("\nroles:\n  office: {label: {it: Uffici amministrativi, en: Administrative offices}}\n", text)
        self.assertIn("      submit: {from: draft, to: pending_director, by: [self.issuer], guard: dataComplete, label: {it: Emetti, en: Submit}}", text)
        self.assertIn("\nreactions:\n  - {name: notify_submitted, event: Invitation.transitioned, when: 'transition in [submit, resubmit]'", text)
        self.assertNotIn("\n\n      '", text)                                                         # folded texts on one line
        # the expressions in their canonical text (to_text normalises parentheses, spaces and folded lines)
        def canon(b):
            e = B.expand(b)
            for cn, ders in e["derivations"].items():
                e["derivations"][cn] = {an: X.to_text(X.parse(str(x))) for an, x in ders.items()}
            return e
        self.assertEqual(canon(B.loads(text)), canon(behavior()))
        # a small behaviour (one derivation, one event, two states) must not fold its blocks into flow mappings
        small = {"roles": {"manager": {}}, "derivations": {"Task": {"ready": "estimateHours.isSet() and assignee.isSet()"}},
                 "workflows": {"Task": {"state": "state", "states": {"todo": {"initial": True}, "done": {"final": True}},
                                        "transitions": {"finish": {"from": "todo", "to": "done", "by": ["manager"]}}}},
                 "events": {"Task": {"expired": {"doc": "late"}}}}
        small_text = B.dumps(small)
        self.assertIn("\nderivations:\n  Task:\n    ready: estimateHours.isSet() and assignee.isSet()\n", small_text)
        self.assertIn("\nworkflows:\n  Task:\n    state: state\n    states:\n      todo: {initial: true}\n      done: {final: true}\n", small_text)
        self.assertIn("\nevents:\n  Task:\n    expired: {doc: late}\n", small_text)
        self.assertIn("\nroles:\n  manager: {}\n", small_text)
        self.assertEqual(B.expand(B.loads(small_text)), B.expand(small))
        # a proposal saved by the web modeler (runtime form) comes back to the structure of the file
        fe = B.from_editor(B.runtime_json(behavior(), meta()))
        self.assertNotIn("entities", fe)
        self.assertNotIn("uses", fe)
        self.assertEqual(fe["workflows"]["Invitation"]["transitions"]["submit"]["from"], "draft")      # one source: a scalar
        self.assertEqual(fe["workflows"]["Invitation"]["transitions"]["submit"]["guard"], "dataComplete")
        self.assertNotIn("final", fe["workflows"]["Invitation"]["states"]["draft"])                     # implicit false dropped
        self.assertEqual(canon(fe), canon(behavior()))
        self.assertEqual(B.validate(fe, meta()).errors, [])
        # the differences a reviewer reads
        new = copy.deepcopy(behavior())
        w = new["workflows"]["Invitation"]
        w["states"]["paused"] = {"label": {"it": "Sospeso"}}
        w["transitions"]["pause"] = {"from": "in_management", "to": "paused", "by": ["office"]}
        w["transitions"]["submit"]["guard"] = "dataComplete and hours > 0"
        del new["reactions"][0]
        new["roles"]["boss"] = {}
        new["derivations"]["Invitation"]["fundsTotal"] = "invitationFunds.amount.sum() + 1"
        self.assertEqual(B.diff(behavior(), new), [
            "+ role boss", "~ derivation Invitation.fundsTotal = invitationFunds.amount.sum() + 1",
            "+ state Invitation.paused", "~ transition Invitation.submit: guard",
            "+ transition Invitation.pause: in_management -> paused", "- reaction notify_submitted"])
        self.assertEqual(B.diff(behavior(), behavior()), [])
        self.assertEqual(B.diff({}, behavior())[:1], ["+ role office"])
        self.assertIn("+ workflow Invitation on state: 11 states, 15 transitions", B.diff({}, behavior()))

    def test_runtime_json(self):
        rj = B.runtime_json(behavior(), meta())
        self.assertEqual(rj["entities"]["Invitation"], "invitation")
        d = rj["derivations"]["Invitation"]["fundsTotal"]
        self.assertEqual((d["text"], d["type"]), ("invitationFunds.amount.sum()", "number"))
        self.assertEqual(d["sql"], "(select coalesce(sum(x1.amount), 0) from public.invitation_funds x1 where x1.invitation = r.id)")
        self.assertEqual(d["ast"]["k"], "path")
        tr = rj["workflows"]["Invitation"]["transitions"]
        self.assertEqual(tr["approve"]["when"]["sql"], "not (r.agency_booking_required)")
        self.assertEqual(tr["approve"]["guard"]["type"], "bool")
        self.assertIsNone(tr["reject"]["guard"])
        self.assertEqual(rj["reactions"][0]["when"]["sql"], "(p_extra -> 'transition' ->> 'key') in ('submit', 'resubmit')")
        self.assertIsNone(rj["reactions"][-1]["when"])
        json.dumps(rj)                                                                  # serializable

    def test_clauses_and_engine_version(self):
        e = E.expand(meta())
        ctx = X.Context(e, "Invitation")
        cl = lambda t: B.clauses(X.check(t, ctx, X.BOOL)[0], e, "Invitation")  # noqa: E731
        self.assertEqual(cl("dataComplete"), [{"field": "data_complete", "op": "is_true"}])
        self.assertEqual(cl("not agencyBookingRequired"), [{"field": "agency_booking_required", "op": "is_false"}])
        self.assertEqual(cl("dataComplete and travelBookingComplete = false"),
                         [{"field": "data_complete", "op": "is_true"}, {"field": "travel_booking_complete", "op": "is_false"}])
        self.assertEqual(cl("compensationType = hourly and hours >= 1 and 2 < hours"),
                         [{"field": "compensation_type", "op": "eq", "value": "hourly"}, {"field": "hours", "op": "gte", "value": 1},
                          {"field": "hours", "op": "gt", "value": 2}])
        self.assertEqual(cl("not (hours > 1)"), [{"field": "hours", "op": "lte", "value": 1}])
        self.assertEqual(cl("travelMethod in [agency, none] and not (mealsMethod in [none])"),
                         [{"field": "travel_method", "op": "in", "value": ["agency", "none"]}, {"field": "meals_method", "op": "not_in", "value": ["none"]}])
        self.assertEqual(cl("reason.isSet() and notes.isEmpty() and not accommodationVenue.isEmpty()"),
                         [{"field": "reason", "op": "is_set"}, {"field": "notes", "op": "is_empty"}, {"field": "accommodation_venue", "op": "is_set"}])
        self.assertEqual(cl("state <> 'draft' and true"), [{"field": "state", "op": "neq", "value": "draft"}])
        for text, frag in [("dataComplete or hours > 0", "is not a clause"), ("reason.code = 'x'", "move navigations and calculations"),
                           ("hours > hourlyRate", "compares with a literal"), ("invitationFunds.size() > 0", "is not a single-valued feature"),
                           ("invitationFunds.notEmpty()", "is not a clause"), ("hours + 1 > 2", "move navigations and calculations"),
                           ("not (dataComplete and hours > 0)", "is not a clause"), ("false", "always false")]:
            with self.assertRaises(X.ExprError, msg=text) as cm:
                cl(text)
            self.assertIn(frag, str(cm.exception), text)
        v = B.engine_version(behavior(), meta(), "Invitation")
        self.assertEqual(v["entity"], "invitation")
        by_key = {t["key"]: t for t in v["transitions"]}
        self.assertEqual(by_key["approve"]["guard"], [{"field": "data_complete", "op": "is_true"}])
        self.assertEqual(by_key["approve"]["condition"], [{"field": "agency_booking_required", "op": "is_false"}])
        self.assertEqual(by_key["approve"]["allowed"], ["director"])
        self.assertEqual(by_key["approve"]["notify"], [{"to": ["office"], "template": "invitation_to_manage"},
                                                       {"to": ["field:issuer"], "template": "invitation_approved"}])
        self.assertEqual((by_key["visit_ended"]["trigger"], by_key["visit_ended"]["at_field"], by_key["visit_ended"]["at_offset"],
                          by_key["visit_ended"]["allowed"], by_key["visit_ended"]["emits"]), ("timed", "end_date", "1 days", [], ["invitation.visit_ended"]))
        self.assertEqual(by_key["withdraw"]["from_states"], ["draft", "rejected"])
        self.assertEqual(by_key["withdraw"]["allowed"], ["field:issuer", "office"])
        self.assertEqual(by_key["reject"]["comment"], "required")
        self.assertEqual(by_key["submit"]["notify"], [{"to": ["director"], "template": "invitation_submitted"}])
        states = {s["key"]: s for s in v["states"]}
        self.assertEqual((states["draft"]["kind"], states["draft"]["owner"], states["draft"]["editable_by"]), ("initial", ["field:issuer"], ["field:issuer", "office"]))
        self.assertEqual((states["awaiting_confirmation"]["reminder_days"], states["awaiting_confirmation"]["reminder_template"]), (7, "visit_confirmation_reminder"))
        self.assertEqual(states["closed"]["kind"], "final")
        self.assertEqual(B.offset_interval("+1d"), "1 days")
        self.assertEqual(B.offset_interval("12h"), "12 hours")
        self.assertEqual(B.offset_interval("2w"), "2 weeks")
        self.assertEqual(B.offset_interval(None), "")
        self.assertEqual(B.principal_key("self.department.createdBy"), "field:department.createdBy")
        b = behavior()
        b["workflows"]["Invitation"]["transitions"]["submit"]["guard"] = "dataComplete or hours > 0"
        with self.assertRaises(X.ExprError):
            B.engine_version(b, meta(), "Invitation")

    def fake_catalog(self):
        v = B.engine_version(behavior(), meta(), "Invitation")
        vid = "00000000-0000-0000-0000-000000000001"
        return {"versions": [{"id": vid, "entity": "invitation", "version": 3, "status": "published"}],
                "states": [{"version_id": vid, **s} for s in copy.deepcopy(v["states"])],
                "transitions": [{"version_id": vid, **t} for t in copy.deepcopy(v["transitions"])]}

    def test_workflow_drift(self):
        cat = self.fake_catalog()
        self.assertEqual(B.workflow_drift(behavior(), meta(), cat), [])
        cat["states"][0]["owner"] = ["office"]
        cat["states"].pop(1)
        cat["states"].append({"version_id": cat["versions"][0]["id"], "key": "limbo", "kind": "normal", "owner": [], "editable_by": []})
        tr = {t["key"]: t for t in cat["transitions"]}
        tr["approve"]["guard"] = []
        tr["approve"]["allowed"] = ["director", "office"]
        tr["visit_ended"]["at_offset"] = "2 days"
        tr["reject"]["comment"] = "optional"
        cat["transitions"] = [t for t in cat["transitions"] if t["key"] != "close"]
        cat["transitions"].append({**tr["reject"], "key": "archive"})
        found = B.workflow_drift(behavior(), meta(), cat)
        for frag in ["STATE invitation.draft: owner database ['office'], model ['field:issuer']", "MISSING STATE invitation.pending_director",
                     "NOT IN MODEL state invitation.limbo", "TRANSITION invitation.approve: guard database [], model ['data_complete is_true None']",
                     "TRANSITION invitation.approve: allowed database ['director', 'office'], model ['director']",
                     "TRANSITION invitation.visit_ended: at_offset database '2 days', model '1 days'",
                     "TRANSITION invitation.reject: comment database 'optional', model 'required'", "MISSING TRANSITION invitation.close",
                     "NOT IN MODEL transition invitation.archive"]:
            self.assertTrue(any(frag in x for x in found), (frag, found))
        self.assertEqual(B.workflow_drift(behavior(), meta(), {"versions": [], "states": [], "transitions": []}),
                         ["WORKFLOW invitation: no published version in the database (behavior.yaml has one for Invitation)"])
        cat = self.fake_catalog()
        cat["versions"].append({"id": "x", "entity": "order", "version": 1, "status": "published"})
        self.assertEqual(B.workflow_drift(behavior(), meta(), cat), ["NOT IN MODEL workflow order (published version in the database)"])
        b = behavior()
        b["workflows"]["Invitation"]["transitions"]["submit"]["guard"] = "dataComplete or hours > 0"
        self.assertTrue(B.workflow_drift(b, meta(), self.fake_catalog())[0].startswith("WORKFLOW invitation: a guard the engine cannot evaluate"))

    def test_sql_view(self):
        sql = B.sql_view(behavior(), meta())
        self.assertIn("-- Invitation: derived attributes (r = a row of public.invitations)", sql)
        self.assertIn("funds_total := (select coalesce(sum(x1.amount), 0) from public.invitation_funds x1 where x1.invitation = r.id);", sql)
        self.assertIn("data_complete := coalesce((r.reason is not null and", sql)
        self.assertIn("--   approve.when: not agencyBookingRequired\ncoalesce(not (r.agency_booking_required), false)", sql)
        self.assertIn("--   notify_submitted on Invitation.transitioned: transition in [submit, resubmit]\n"
                      "coalesce((p_extra -> 'transition' ->> 'key') in ('submit', 'resubmit'), false)", sql)


class SyncAndCommandTests(unittest.TestCase):
    def run_cli(self, *args):
        import contextlib
        import io
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_sync_writes_behavior_json_and_docs(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "domain.ecore.yaml").write_text(META.read_text())
            self.assertEqual(sorted(cli.sync(root)), ["docs/DOMAIN.md", "src/lib/modeler/metamodel.json"])
            (root / "behavior.yaml").write_text(BEHAVIOR.read_text())
            written = cli.sync(root)
            self.assertEqual(sorted(written), ["docs/BEHAVIOR.md", "docs/DOMAIN.md", "src/lib/modeler/behavior.json", "src/lib/modeler/metamodel.json"])
            md = (root / "docs" / "BEHAVIOR.md").read_text()
            self.assertTrue(md.startswith(B.MARKDOWN_MARK))
            self.assertIn("## Workflow of Invitation", md)
            data = json.loads((root / "src/lib/modeler/behavior.json").read_text())
            self.assertEqual(data["entities"]["Invitation"], "invitation")
            # always rewritten (no hand notes)
            (root / "docs" / "BEHAVIOR.md").write_text("edited\n")
            cli.sync(root)
            self.assertIn("## Workflow of Invitation", (root / "docs" / "BEHAVIOR.md").read_text())
            # a broken behaviour is not generated
            (root / "behavior.yaml").write_text(BEHAVIOR.read_text().replace("guard: dataComplete,", "guard: nope,", 1))
            self.assertEqual(sorted(cli.sync(root)), ["docs/DOMAIN.md", "src/lib/modeler/metamodel.json"])
            (root / "behavior.yaml").write_text(BEHAVIOR.read_text())
            # another document named behavior.md (other case): BEHAVIOR.md is not written
            (root / "docs" / "BEHAVIOR.md").unlink()
            (root / "docs" / "behavior.md").write_text("# hand written\n")
            self.assertEqual(sorted(cli.sync(root)), ["docs/DOMAIN.md", "src/lib/modeler/behavior.json", "src/lib/modeler/metamodel.json"])
            self.assertEqual(cli.docs_clash(root, cli.BEHAVIOR_MD), "docs/behavior.md")
            self.assertIsNone(cli.docs_clash(root))

    def test_behavior_command(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "domain.ecore.yaml").write_text(META.read_text())
            code, out, err = self.run_cli("behavior", str(root / "domain.ecore.yaml"))
            self.assertEqual(code, 1)
            self.assertIn("no behavior.yaml", err)
            (root / "behavior.yaml").write_text(BEHAVIOR.read_text())
            code, out, _ = self.run_cli("behavior", str(root / "domain.ecore.yaml"))
            self.assertEqual(code, 0)
            self.assertIn("# Behaviour of the domain invitations", out)
            code, out, _ = self.run_cli("behavior", str(root / "domain.ecore.yaml"), "--lang", "it")
            self.assertIn("# Comportamento del dominio invitations", out)
            code, out, _ = self.run_cli("behavior", str(root / "domain.ecore.yaml"), "--format", "mermaid")
            self.assertIn("%% Invitation\nstateDiagram-v2", out)
            code, out, _ = self.run_cli("behavior", str(root / "domain.ecore.yaml"), "--format", "json")
            self.assertEqual(json.loads(out)["entities"]["Invitation"], "invitation")
            code, out, _ = self.run_cli("behavior", str(root / "domain.ecore.yaml"), "--format", "sql")
            self.assertIn("funds_total :=", out)
            code, out, _ = self.run_cli("behavior", str(root / "domain.ecore.yaml"), "--format", "engine")
            self.assertEqual(json.loads(out)["Invitation"]["transitions"][0]["key"], "submit")
            (root / "behavior.yaml").write_text(BEHAVIOR.read_text().replace("guard: dataComplete,", "guard: dataComplete or hours > 0,", 1))
            code, out, err = self.run_cli("behavior", str(root / "domain.ecore.yaml"), "--format", "engine")
            self.assertEqual(code, 1)
            self.assertIn("a guard the engine cannot evaluate as clauses", err)
            (root / "behavior.yaml").write_text(BEHAVIOR.read_text().replace("guard: dataComplete,", "guard: nope,", 1))
            code, out, err = self.run_cli("behavior", str(root / "domain.ecore.yaml"))
            self.assertEqual(code, 1)
            self.assertIn("'nope' is not a feature", err)
            code, out, _ = self.run_cli("behavior", str(META), "--behavior", str(BEHAVIOR), "--format", "mermaid")
            self.assertEqual(code, 0)

    def test_hook_on_generated_behavior_md(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "domain.ecore.yaml").write_text(META.read_text())
            (root / "docs").mkdir()
            (root / "docs" / "BEHAVIOR.md").write_text("x\n")
            out = subprocess.run([sys.executable, str(ROOT / "hooks" / "hook.py"), "post"],
                                 input=json.dumps({"tool_input": {"file_path": str(root / "docs" / "BEHAVIOR.md")}}), capture_output=True, text=True)
            self.assertEqual(out.returncode, 0)
            self.assertIn("generated from behavior.yaml", out.stdout)


@unittest.skipUnless(os.environ.get("MODELER_PG"), "MODELER_PG not set")
class WorkflowDatabaseTests(unittest.TestCase):
    """The generated SQL runs on PostgreSQL, and drift compares the workflows with the engine's tables."""

    ENGINE = """
    create table public.workflow_versions (id uuid primary key default gen_random_uuid(), entity text not null, version int not null,
      status text not null default 'draft', unique (entity, version));
    create table public.workflow_states (version_id uuid references public.workflow_versions (id), key text not null, labels jsonb default '{}',
      kind text not null default 'normal', color text not null default '#64748b', owner text[] not null default '{}',
      editable_by text[] not null default '{}', reminder_days int, reminder_template text, sort int not null default 0, primary key (version_id, key));
    create table public.workflow_transitions (version_id uuid references public.workflow_versions (id), key text not null, labels jsonb default '{}',
      from_states text[] not null default '{}', to_state text not null, allowed text[] not null default '{}', trigger text not null default 'manual',
      at_field text, at_offset text not null default '', comment text not null default 'optional', guard jsonb not null default '[]',
      condition jsonb not null default '[]', emits text[] not null default '{}', notify jsonb not null default '[]', sort int not null default 0,
      primary key (version_id, key));
    """

    def setUp(self):
        self.base = os.environ["MODELER_PG"]
        self.db = f"modeler_{uuid.uuid4().hex[:8]}"
        self.psql(self.base, f"create database {self.db}")
        self.dsn = self.base.rsplit("/", 1)[0] + "/" + self.db

    def tearDown(self):
        subprocess.run(["psql", self.base, "-qc", f"drop database {self.db} with (force)"], capture_output=True)

    def psql(self, dsn, sql):
        out = subprocess.run(["psql", dsn, "-q", "-v", "ON_ERROR_STOP=1", "-c", sql], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        return out.stdout

    def seed(self, root):
        from metamodel import sqlgen as G
        sql, _ = G.migration({"package": "invitations", "classes": {}}, meta(), "whole")
        # the generated migration: tables, enums, foreign keys; profiles stands for the users
        self.psql(self.dsn, "create table public.profiles (id uuid primary key default gen_random_uuid(), email text);")
        self.psql(self.dsn, sql)
        self.psql(self.dsn, self.ENGINE)
        v = B.engine_version(behavior(), meta(), "Invitation")
        self.psql(self.dsn, "insert into public.workflow_versions (id, entity, version, status) values "
                            "('00000000-0000-0000-0000-000000000001', 'invitation', 1, 'published');")
        for s in v["states"]:
            self.psql(self.dsn, "insert into public.workflow_states (version_id, key, kind, owner, editable_by, reminder_days, reminder_template, sort) values "
                                f"('00000000-0000-0000-0000-000000000001', '{s['key']}', '{s['kind']}', "
                                f"array[{', '.join(repr(x) for x in s['owner'])}]::text[], array[{', '.join(repr(x) for x in s['editable_by'])}]::text[], "
                                f"{s['reminder_days'] if s['reminder_days'] is not None else 'null'}, "
                                f"{repr(s['reminder_template']) if s['reminder_template'] else 'null'}, {s['sort']});")
        for t in v["transitions"]:
            self.psql(self.dsn, "insert into public.workflow_transitions (version_id, key, from_states, to_state, allowed, trigger, at_field, at_offset, "
                                "comment, guard, condition, emits, sort) values "
                                f"('00000000-0000-0000-0000-000000000001', '{t['key']}', array[{', '.join(repr(x) for x in t['from_states'])}]::text[], "
                                f"'{t['to_state']}', array[{', '.join(repr(x) for x in t['allowed'])}]::text[], '{t['trigger']}', "
                                f"{repr(t['at_field']) if t['at_field'] else 'null'}, '{t['at_offset']}', '{t['comment']}', "
                                f"'{json.dumps(t['guard'])}'::jsonb, '{json.dumps(t['condition'])}'::jsonb, "
                                f"array[{', '.join(repr(x) for x in t['emits'])}]::text[], {t['sort']});")

    def test_generated_sql_runs_and_workflows_align(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "domain.ecore.yaml").write_text(META.read_text())
            (root / "behavior.yaml").write_text(BEHAVIOR.read_text())
            self.seed(root)
            # every derivation, guard and condition is valid SQL on a row of the table
            rj = B.runtime_json(behavior(), meta())
            exprs = [x["sql"] for x in rj["derivations"]["Invitation"].values()]
            exprs += [tr[k]["sql"] for tr in rj["workflows"]["Invitation"]["transitions"].values() for k in ("when", "guard") if tr[k]]
            self.psql(self.dsn, "select " + ", ".join(f"({x})" for x in exprs) + " from public.invitations r;")
            self.psql(self.dsn, "insert into public.invitation_reasons (code, label, compensation_type) values ('sem', 'Seminar', 'hourly');")
            self.psql(self.dsn, "insert into public.departments (code, name) values ('cs', 'CS'); "
                                "insert into public.guests (last_name, first_name, email, home_institution) values ('Doe', 'J', 'j@x.org', 'X'); "
                                "insert into public.profiles (id) values ('00000000-0000-0000-0000-00000000000a');")
            self.psql(self.dsn, "insert into public.invitations (code, start_date, end_date, hours, hourly_rate, meals_method, meals_amount, "
                                "compensation_type, state, department, guest, reason, created_by) "
                                "select 'INV-1', '2026-01-10', '2026-01-13', 2, 50, 'receipts', 80, 'hourly', 'draft', "
                                "d.id, g.id, rz.id, '00000000-0000-0000-0000-00000000000a' from public.departments d, public.guests g, public.invitation_reasons rz;")
            der = rj["derivations"]["Invitation"]
            out = subprocess.run(["psql", self.dsn, "-X", "-A", "-t", "-c",
                                  f"select {der['compensationType']['sql']}, {der['compensationAmount']['sql']}, {der['mealsPerDay']['sql']}, "
                                  f"{der['agencyBookingRequired']['sql']}, {der['fundsTotal']['sql']} from public.invitations r"],
                                 capture_output=True, text=True)
            self.assertEqual(out.stdout.strip(), "hourly|100.00|20.00|f|0", out.stderr)
            self.assertFalse(D.has_record_url(self.dsn))                                # drift reports it: the texts use {{url}}
            self.psql(self.dsn, "create function public.record_url(entity text, id uuid) returns text language sql as $$ select '/x/' || entity || '/' || id $$;")
            self.assertTrue(D.has_record_url(self.dsn))
            cat = D.workflow_catalog(self.dsn)
            self.assertEqual(cat["versions"][0]["entity"], "invitation")
            self.assertEqual(B.workflow_drift(behavior(), meta(), cat), [])
            self.psql(self.dsn, "update public.workflow_transitions set guard = '[]'::jsonb where key = 'approve';")
            found = B.workflow_drift(behavior(), meta(), D.workflow_catalog(self.dsn))
            self.assertEqual(len(found), 1)
            self.assertIn("TRANSITION invitation.approve: guard database []", found[0])
            self.psql(self.dsn, "drop table public.workflow_transitions, public.workflow_states, public.workflow_versions;")
            self.assertIsNone(D.workflow_catalog(self.dsn))


class EngineTests(unittest.TestCase):
    def test_engine_sql_text(self):
        from metamodel import engine as N
        sql, notes = N.engine_sql(behavior(), meta())
        self.assertIn("jsonb_build_object('recipients'", sql)      # every emitted event carries `recipients`, [] when nobody
        # the contract: who really acts (null unless «view as» is on), kept by the history and the events
        self.assertIn("if to_regprocedure('public.impersonator_id()') is null then", sql)
        self.assertIn("alter table public.workflow_history alter column impersonated_by set default public.impersonator_id();", sql)
        self.assertIn("|| jsonb_strip_nulls(jsonb_build_object('impersonated_by', public.impersonator_id()))", sql)
        self.assertNotIn("View as", sql)
        self.assertNotIn("view_as_profile_id", sql)
        va = behavior()
        va["view_as"] = {"users_by": ["admin", "office"]}
        vsql, _ = N.engine_sql(va, meta())
        for frag in ["-- ===================== View as =====================",
                     "alter function public.current_profile_id() rename to real_profile_id;",
                     "alter function public.has_role(text, uuid) rename to has_role_real;",
                     "if to_regprocedure('public.view_as_allowed(uuid)') is null then",
                     "v_ok := public.has_role_real('admin', null) or public.has_role_real('office', null);",
                     "if coalesce(current_setting('app.view_as_resolving', true), '') = 'on' then return null; end if;",
                     "v_raw := nullif(current_setting('request.headers', true), '')::json ->> 'x-view-as-user';",
                     "select coalesce(public.view_as_profile_id(), public.real_profile_id());",
                     "select case when public.view_as_profile_id() is not null then public.real_profile_id() end;",
                     "'select (public.view_as_role() is null or public.view_as_role() = p_role::text) and public.has_role_real(p_role, p_scope)'",
                     "create table if not exists public.view_as_log (",
                     "create or replace function public.view_as_audit(p_profile uuid, p_start boolean)",
                     "perform public.emit_entity_event('profile', p_profile, case when p_start then 'user.view_as_started' else 'user.view_as_ended' end,",
                     "create or replace function public.view_as_log(p_limit int default 20)",
                     "register: user.view_as_started, user.view_as_ended, invitation.created",
                     "view as: the Supabase server client sends the headers x-view-as / x-view-as-user"]:
            self.assertIn(frag, vsql)
        for frag in ["create or replace function public.invitation_principals(r public.invitations)",
                     "case when r.issuer = public.current_profile_id() then 'field:issuer' end",
                     "case when public.has_role('director', r.department) then 'director' end",
                     "create or replace function public.invitation_recipients(r public.invitations, p_to text[], p_template text, p_extra jsonb default '{}'::jsonb)",
                     "create or replace function public.render_template(p_text text, p_vars jsonb)",
                     "create or replace function public.invitation_template_vars(r public.invitations, p_extra jsonb default '{}'::jsonb)",
                     "'self.startDate', (r.start_date)::text", "'invitation.startDate', (r.start_date)::text",
                     "when 'submit' then 'Submit'", "'state.label', case r.state", "when 'draft' then 'Draft'",
                     "execute 'select public.record_url($1, $2)' into v_url using 'invitation', r.id;",
                     "when 'invitation_submitted' then 'Invitation {{self.id}} to approve'",
                     "execute 'select t.subject, t.body from public.notification_templates t where t.key = $1 and t.locale = $2'",
                     "'subject', public.render_template(v_subject, v_vars), 'body', public.render_template(v_body, v_vars)",
                     "select p.email as email, 'director' as kind from public.role_members('director', r.department) m join public.profiles p on p.id = m where 'director' = any (p_to)",
                     "select x1.email as email, 'field:guest.email' as kind from public.guests x1 where x1.id = r.guest and 'field:guest.email' = any (p_to)",
                     "select p.email as email, 'field:issuer' as kind from public.profiles p where 'field:issuer' = any (p_to) and p.id = r.issuer",
                     "if p_type = 'invitation.transitioned' and coalesce((p_extra -> 'transition' ->> 'key') in ('submit', 'resubmit'), false) then",
                     "v := v || public.invitation_recipients(r, array['director']::text[], 'invitation_submitted', p_extra);",
                     "if p_type = 'invitation.reverted' and true then",
                     "new.funds_total := (select coalesce(sum(x1.amount), 0) from public.invitation_funds x1 where x1.invitation = new.id);",
                     "new.data_complete := coalesce((new.reason is not null and",
                     "create trigger invitation_20_derive before insert or update on public.invitations",
                     "create or replace function public.invitation_fund_refresh_invitation()",
                     "update public.invitations x set id = x.id where x.id in (new.invitation, old.invitation);",
                     "create or replace function public.invitation_reason_refresh_invitation()",
                     "update public.invitations x set id = x.id where x.reason in (new.id, old.id);",
                     "if new.state is null then new.state := 'draft'; end if;",
                     "raise exception 'Transition not available: %', p_key;",
                     # the list is a plain array of objects, not rows wrapped in {"jsonb_build_object": …}
                     "return coalesce((select jsonb_agg(t.j) from (",
                     "'guard_ok', coalesce(r.data_complete, false), 'guard', 'dataComplete') as j\n     where r.state = any (array['draft']::text[])",
                     "if p_key = 'approve' then\n    v_from := array['pending_director']::text[]; v_to := 'in_management'; v_allowed := array['director']::text[];",
                     "v_cond := coalesce(not (r.agency_booking_required), false);",
                     "v_guard := coalesce(r.data_complete, false); v_guard_text := 'dataComplete';",
                     "elsif p_key = 'visit_ended' then", "v_timed := true;",
                     "for v_id in select x.id from public.invitations x where x.state = any (array['in_management']::text[]) and x.end_date + interval '1 days' <= now() loop",
                     "perform public.invitation_perform_transition(v_id, 'visit_ended', null, true);",
                     "when 'awaiting_confirmation' then interval '7 days'", "when 'awaiting_confirmation' then 'visit_confirmation_reminder'",
                     "create or replace function public.invitation_revert(p_id uuid, p_state text, p_comment text default null)",
                     "create trigger invitation_90_lifecycle after insert or update or delete on public.invitations",
                     "-- TODO(modeler): if the application keeps a catalogue of event types", "invitation.visit_ended",
                     "select cron.schedule('invitation_timed'"]:
            self.assertIn(frag, sql, frag)
        self.assertNotIn("r.guest = public.current_profile_id()", sql)          # an email recipient is not an actor
        self.assertEqual(N.engine_sql(behavior(), meta())[0].count("create or replace function"), sql.count("create or replace function"))
        m = meta()
        m["language"] = "it"
        sql_it, _ = N.engine_sql(behavior(), m)
        self.assertIn("raise exception 'Requisiti non soddisfatti: %', v_guard_text;", sql_it)
        # a state that requires fields: the entering transitions list what is missing, the trigger keeps the invariant
        b = behavior()
        b["workflows"]["Invitation"]["states"]["pending_director"]["requires"] = ["hours", "invitationFunds"]
        sql, _ = N.engine_sql(b, meta())
        for frag in ["v_cond boolean; v_guard boolean; v_guard_text text; v_missing text[];",
                     "v_missing := array_remove(array[case when not coalesce(r.hours is not null, false) then 'hours' end, "
                     "case when not coalesce(exists (select 1 from public.invitation_funds x1 where x1.invitation = r.id), false) then 'invitationFunds' end]::text[], null);",
                     "if cardinality(v_missing) > 0 then raise exception 'Required in state %: %', v_to, array_to_string(v_missing, ', ') using errcode = '23514'; end if;",
                     "'guard_ok', (coalesce(r.data_complete, false) and cardinality(array_remove(array[case when not coalesce(r.hours is not null, false) then 'hours' end",
                     "'guard', 'dataComplete', 'missing', to_jsonb(array_remove(array[",
                     "  if new.state = 'pending_director' and not coalesce(new.hours is not null, false) then\n"
                     "    raise exception 'Required in state %: %', 'pending_director', 'hours' using errcode = '23514';\n  end if;",
                     "elsif new.state is distinct from old.state and coalesce(current_setting('app.in_transition', true), '') <> 'on' then"]:
            self.assertIn(frag, sql, frag)
        self.assertNotIn("new.state = 'pending_director' and not coalesce(exists", sql)   # a collection is checked only on entering
        self.assertIn("v_missing := '{}'::text[];", sql)                                   # transitions to states without requires
        self.assertIn("raise exception 'Campi richiesti nello stato %: %'", N.engine_sql(b, m)[0])
        self.assertTrue(any("schedule public.invitation_run_timed_transitions()" in n for n in notes))
        # the state's model: read only and allowed literals as invariants of the trigger, `in` among the missing ones on
        # entering, and <entity>_field_policy(r) for the forms
        b = behavior()
        b["workflows"]["Invitation"]["states"]["pending_director"]["model"] = {
            "flatAmount": {"lower": 1, "readonly": True}, "notes": {"hidden": True}, "travelMethod": {"in": ["agency", "receipts"]}}
        sql, _ = N.engine_sql(b, meta())
        for frag in ["  if tg_op = 'UPDATE' and new.state = 'pending_director' and old.state = 'pending_director' and new.flat_amount is distinct from old.flat_amount then\n"
                     "    raise exception 'Read only in state %: %', 'pending_director', 'flatAmount' using errcode = '23514';\n  end if;",
                     "and new.notes is distinct from old.notes then\n    raise exception 'Read only in state %: %', 'pending_director', 'notes'",
                     "  if new.state = 'pending_director' and new.travel_method is not null and new.travel_method not in ('agency', 'receipts') then\n"
                     "    raise exception 'Not allowed in state %: %', 'pending_director', 'travelMethod' using errcode = '23514';\n  end if;",
                     "case when not coalesce((r.travel_method is null or r.travel_method in ('agency', 'receipts')), false) then 'travelMethod' end]::text[], null);",
                     "create or replace function public.invitation_field_policy(r public.invitations)",
                     "    when 'pending_director' then jsonb_build_object('flatAmount', jsonb_build_object('required', true, 'readonly', true, 'hidden', false), "
                     "'notes', jsonb_build_object('required', false, 'readonly', true, 'hidden', true), "
                     "'travelMethod', jsonb_build_object('required', false, 'readonly', false, 'hidden', false, 'in', array['agency', 'receipts']::text[]))",
                     "    else '{}'::jsonb end;",
                     "_field_policy(r) says which fields are required, read only, hidden or limited"]:
            self.assertIn(frag, sql, frag)
        self.assertNotIn("new.notes is not null", sql)                                          # hidden is not required
        self.assertIn("raise exception 'Sola lettura nello stato %: %'", N.engine_sql(b, m)[0])
        self.assertIn("raise exception 'Valore non ammesso nello stato %: %'", N.engine_sql(b, m)[0])
        self.assertIn("  select '{}'::jsonb;", N.engine_sql(behavior(), meta())[0])             # no overlay: an empty policy
        # a class with derivations but no workflow still gets its derive trigger, nothing else of the workflow
        b = behavior()
        b["derivations"]["Guest"] = {"fullName": "coalesce(lastName, '') + ' ' + coalesce(firstName, '')"}
        m = meta()
        m["classes"]["Guest"]["attributes"]["fullName"] = {"type": "EString", "derived": True}
        with self.assertRaises(X.ExprError):                                     # no string arithmetic
            N.engine_sql(b, m)
        b["derivations"]["Guest"] = {"fullName": "if lastName.isSet() then lastName else firstName"}
        sql, _ = N.engine_sql(b, m)
        self.assertIn("create or replace function public.guest_derive()", sql)
        self.assertNotIn("guest_perform_transition", sql)

    def test_creator_needs_created_by(self):
        b = behavior()
        b["reactions"].append({"name": "x", "event": "Invitation.created", "notify": ["creator"], "template": "t"})
        self.assertEqual(errors(b), [])
        m = meta()
        m["classes"]["Invitation"]["references"].pop("createdBy")
        self.assertTrue(any("'creator' needs a reference createdBy: User on Invitation" in x for x in errors(b, m)))

    def test_engine_command(self):
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "domain.ecore.yaml").write_text(META.read_text())
            (root / "behavior.yaml").write_text(BEHAVIOR.read_text())
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cli.main(["engine", str(root / "domain.ecore.yaml")])
            self.assertEqual(code, 0)
            self.assertIn("invitation_perform_transition", out.getvalue())
            self.assertIn("dry run", err.getvalue())
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = cli.main(["engine", str(root / "domain.ecore.yaml"), "--write", "--name", "Behaviour Engine"])
            self.assertEqual(code, 0)
            files = list((root / "supabase" / "migrations").glob("*_behaviour_engine.sql"))
            self.assertEqual(len(files), 1)
            self.assertIn("TODO(modeler) to review", out.getvalue())
            # regenerated: the previous engine migration is replaced by one with a later timestamp
            (root / "supabase" / "migrations" / "99990101000000_schema.sql").write_text("select 1;\n")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(cli.main(["engine", str(root / "domain.ecore.yaml"), "--write", "--name", "Behaviour Engine"]), 0)
            after = list((root / "supabase" / "migrations").glob("*_behaviour_engine.sql"))
            self.assertEqual(len(after), 1)
            self.assertNotEqual(after[0].name, files[0].name)
            self.assertGreater(after[0].name, "99990101000000_schema.sql")           # after every existing migration
            self.assertRegex(out.getvalue(), rf"replaced .*/{files[0].name}\n")


@unittest.skipUnless(os.environ.get("MODELER_PG"), "MODELER_PG not set")
class EngineDatabaseTests(WorkflowDatabaseTests):
    """The generated engine runs the guest-invitations workflow end to end on PostgreSQL."""

    ISSUER = "00000000-0000-0000-0000-00000000000a"
    DIRECTOR = "00000000-0000-0000-0000-00000000000b"
    OFFICE = "00000000-0000-0000-0000-00000000000c"
    OTHER = "00000000-0000-0000-0000-00000000000d"

    def as_user(self, user, sql):
        return subprocess.run(["psql", self.dsn, "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-c",
                               f"set app.profile_id = '{user}'; {sql}"], capture_output=True, text=True)

    def ok(self, user, sql):
        out = self.as_user(user, sql)
        self.assertEqual(out.returncode, 0, out.stderr)
        return out.stdout.strip().split("\n")[-1] if out.stdout.strip() else ""

    def system(self, sql):
        """As the scheduler runs: no user in the session."""
        out = subprocess.run(["psql", self.dsn, "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-c", sql], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        return out.stdout.strip()

    def fails(self, user, sql, fragment):
        out = self.as_user(user, sql)
        self.assertNotEqual(out.returncode, 0, out.stdout)
        self.assertIn(fragment, out.stderr)

    ADMIN = "00000000-0000-0000-0000-00000000000e"

    def view_as_checks(self, inv):
        """«View as» on the same database: an administrator acts as the issuer, the office restricts its role."""
        from metamodel import engine as N
        va = behavior()
        va["view_as"] = {"users_by": ["admin"]}
        self.psql(self.dsn, N.engine_sql(va, meta())[0])
        self.psql(self.dsn, N.engine_sql(va, meta())[0])                                  # idempotent (renames once)
        self.psql(self.dsn, f"insert into public.profiles (id, email) values ('{self.ADMIN}', 'admin@x.org');"
                            f"insert into public.user_roles values ('{self.ADMIN}', 'admin', null);")
        as_issuer = f"select set_config('request.headers', '{{\"x-view-as-user\": \"{self.ISSUER}\"}}', false);"
        self.assertEqual(self.ok(self.ADMIN, as_issuer + "select current_profile_id() || '|' || impersonator_id() || '|' || is_admin();"),
                         f"{self.ISSUER}|{self.ADMIN}|false")
        self.assertEqual(self.ok(self.OTHER, as_issuer + "select current_profile_id() || '|' || coalesce(impersonator_id()::text, '-');"),
                         f"{self.OTHER}|-")                                              # not allowed to: the header is ignored
        # what the administrator does as someone is that someone's, with the administrator next to it
        as_director = f"select set_config('request.headers', '{{\"x-view-as-user\": \"{self.DIRECTOR}\"}}', false);"
        self.ok(self.ADMIN, as_issuer + "update public.invitations set notes = 'seen by the admin as the issuer';")
        self.fails(self.ADMIN, as_issuer + f"select public.invitation_perform_transition({inv}, 'reject', 'as the issuer');", "Operation not allowed")   # the issuer cannot
        self.ok(self.ADMIN, as_director + f"select public.invitation_perform_transition({inv}, 'reject', 'as the director');")
        self.assertEqual(self.ok(self.ISSUER, "select actor_id || '|' || impersonated_by from public.workflow_history where transition = 'reject';"),
                         f"{self.DIRECTOR}|{self.ADMIN}")
        ev = self.ok(self.ISSUER, "select data from public.events where type = 'invitation.transitioned' and data -> 'transition' ->> 'key' = 'reject';")
        self.assertIn(f'"impersonated_by": "{self.ADMIN}"', ev)
        self.ok(self.ADMIN, as_issuer + f"select public.invitation_perform_transition({inv}, 'resubmit');")       # back where the test was
        self.assertEqual(self.ok(self.ISSUER, "select state from public.invitations;"), "pending_director")
        # the role restriction keeps one of the user's own roles, never adds one
        as_office = "select set_config('request.headers', '{\"x-view-as\": \"office\"}', false);"
        self.assertEqual(self.ok(self.OFFICE, as_office + "select has_role('office', null) || '|' || is_admin();"), "true|false")
        self.assertEqual(self.ok(self.ADMIN, as_office + "select has_role('office', null) || '|' || is_admin();"), "false|true")     # not held: ignored
        self.assertEqual(self.ok(self.DIRECTOR, as_office + "select has_role('director', null);"), "t")                           # not held: ignored
        self.psql(self.dsn, f"insert into public.user_roles values ('{self.OFFICE}', 'director', null);")                            # two roles: one kept
        self.assertEqual(self.ok(self.OFFICE, as_office + "select has_role('director', null) || '|' || has_role('office', null);"), "false|true")
        self.assertEqual(self.ok(self.OFFICE, "select has_role('director', null) || '|' || has_role('office', null);"), "true|true")  # no header: all of them
        self.psql(self.dsn, f"delete from public.user_roles where profile_id = '{self.OFFICE}' and role = 'director';")
        # the register
        self.ok(self.ADMIN, f"select public.view_as_audit('{self.ISSUER}', true);")
        self.ok(self.ADMIN, f"select public.view_as_audit('{self.ISSUER}', false);")
        self.fails(self.OFFICE, f"select public.view_as_audit('{self.ISSUER}', true);", "Operation not allowed")
        self.fails(self.ADMIN, f"select public.view_as_audit('{self.ADMIN}', true);", "Operation not allowed")
        self.assertEqual(self.ok(self.ADMIN, "select string_agg(started::text || ':' || actor_email || '>' || user_email, ',' order by occurred_at) from public.view_as_log(5);"),
                         "true:admin@x.org>issuer@x.org,false:admin@x.org>issuer@x.org")
        self.assertEqual(self.ok(self.OFFICE, "select count(*) from public.view_as_log(5);"), "0")
        self.assertEqual(self.ok(self.ADMIN, "select count(*) from public.events where type in ('user.view_as_started', 'user.view_as_ended');"), "2")
        self.psql(self.dsn, N.engine_sql(behavior(), meta())[0])                            # the fixture's engine again: has_role stays wrapped, harmless

    def test_workflow_end_to_end(self):
        from metamodel import engine as N
        from metamodel import sqlgen as G
        sql, _ = G.migration({"package": "invitations", "classes": {}}, meta(), "whole")
        self.psql(self.dsn, "create table public.profiles (id uuid primary key default gen_random_uuid(), email text);"
                            "create table public.user_roles (profile_id uuid references public.profiles (id), role text not null, scope_id uuid);"
                            "do $r$ begin if not exists (select 1 from pg_roles where rolname = 'authenticated') then "
                            "create role authenticated nologin; end if; end $r$;")
        self.psql(self.dsn, sql)
        engine, _ = N.engine_sql(behavior(), meta())
        self.psql(self.dsn, engine)
        self.psql(self.dsn, engine)                                                      # idempotent
        self.psql(self.dsn, f"insert into public.profiles (id, email) values ('{self.ISSUER}', 'issuer@x.org'), ('{self.DIRECTOR}', 'dir@x.org'), "
                            f"('{self.OFFICE}', 'office@x.org'), ('{self.OTHER}', 'other@x.org');"
                            "insert into public.departments (code, name) values ('cs', 'CS');"
                            f"insert into public.user_roles select '{self.DIRECTOR}', 'director', id from public.departments;"
                            f"insert into public.user_roles values ('{self.OFFICE}', 'office', null);"
                            "insert into public.invitation_reasons (code, label, compensation_type) values ('sem', 'Seminar', 'hourly');"
                            "insert into public.guests (last_name, first_name, email, home_institution) values ('Doe', 'J', 'guest@y.org', 'Y');")
        self.ok(self.ISSUER, "insert into public.invitations (code, start_date, end_date, hours, hourly_rate, meals_method, meals_amount, "
                             "department, guest, reason, issuer, created_by) select 'INV-1', '2027-01-10', '2027-01-13', 2, 50, 'receipts', 80, "
                             f"d.id, g.id, rz.id, '{self.ISSUER}', '{self.ISSUER}' from public.departments d, public.guests g, public.invitation_reasons rz;")
        row = self.ok(self.ISSUER, "select state || '|' || compensation_type || '|' || compensation_amount || '|' || total_amount || '|' || funds_total "
                                   "|| '|' || data_complete || '|' || meals_per_day from public.invitations;")
        self.assertEqual(row, "draft|hourly|100.00|180.00|0|false|20.00")                   # the state and the derived attributes on insert
        self.assertEqual(self.ok(self.ISSUER, "select count(*) from public.events where type = 'invitation.created';"), "1")
        inv = "(select id from public.invitations)"
        avail = self.ok(self.ISSUER, f"select public.invitation_available_transitions({inv});")
        self.assertIn('"key": "submit"', avail)
        self.assertIn('"guard_ok": false', avail)
        self.assertNotIn('"key": "approve"', avail)
        self.fails(self.ISSUER, f"select public.invitation_perform_transition({inv}, 'submit');", "Requirements not met: dataComplete")
        self.fails(self.ISSUER, "update public.invitations set state = 'closed';", "The state changes only through the transitions")
        # the funds complete the data: the child table refreshes the parent's derived attributes
        self.ok(self.ISSUER, "with f as (insert into public.funds (name) values ('F1') returning id) "
                             f"insert into public.invitation_funds (amount, invitation, fund, created_by) select 180, i.id, f.id, '{self.ISSUER}' "
                             "from public.invitations i, f;")
        self.assertEqual(self.ok(self.ISSUER, "select funds_total || '|' || data_complete from public.invitations;"), "180|true")
        self.assertIn('"guard_ok": true', self.ok(self.ISSUER, f"select public.invitation_available_transitions({inv});"))
        # a field required from pending_director: submit names it among the missing ones; once there it cannot be cleared
        req = behavior()
        req["workflows"]["Invitation"]["states"]["pending_director"]["requires"] = ["flatAmount"]   # not read by dataComplete (hourly)
        req["workflows"]["Invitation"]["states"]["pending_director"]["model"] = {"flatAmount": {"readonly": True}, "travelMethod": {"in": ["none", "agency"]}}
        self.psql(self.dsn, N.engine_sql(req, meta())[0])
        self.assertEqual(self.ok(self.ISSUER, "select public.invitation_field_policy(i) from public.invitations i;"), "{}")   # draft: as the metamodel
        self.assertIn('"missing": ["flatAmount"]', self.ok(self.ISSUER, f"select public.invitation_available_transitions({inv});"))
        self.fails(self.ISSUER, f"select public.invitation_perform_transition({inv}, 'submit');", "Required in state pending_director: flatAmount")
        self.ok(self.ISSUER, "update public.invitations set flat_amount = 10;")
        self.assertIn('"missing": [], "guard_ok": true', self.ok(self.ISSUER, f"select public.invitation_available_transitions({inv});"))
        self.fails(self.OTHER, f"select public.invitation_perform_transition({inv}, 'submit');", "Operation not allowed")
        self.assertEqual(self.ok(self.OTHER, f"select public.invitation_available_transitions({inv});"), "[]")
        self.ok(self.ISSUER, f"select public.invitation_perform_transition({inv}, 'submit');")
        self.assertEqual(self.ok(self.ISSUER, "select state from public.invitations;"), "pending_director")
        self.fails(self.ISSUER, "update public.invitations set flat_amount = null;", "Required in state pending_director: flatAmount")
        self.fails(self.ISSUER, "update public.invitations set flat_amount = 20;", "Read only in state pending_director: flatAmount")
        self.fails(self.ISSUER, "update public.invitations set travel_method = 'receipts';", "Not allowed in state pending_director: travelMethod")
        self.ok(self.ISSUER, "update public.invitations set notes = 'ok';")                   # not in the model: free
        policy = self.ok(self.ISSUER, "select public.invitation_field_policy(i) from public.invitations i;")
        self.assertIn('"flatAmount": {"hidden": false, "readonly": true, "required": true}', policy)
        self.assertIn('"travelMethod": {"in": ["none", "agency"], "hidden": false, "readonly": false, "required": false}', policy)
        self.psql(self.dsn, engine)                                                      # back to the fixture's engine
        self.assertEqual(self.ok(self.ISSUER, "select transition || '|' || from_state || '|' || to_state || '|' || actor_id || '|' || coalesce(impersonated_by::text, '-') from public.workflow_history;"),
                         f"submit|draft|pending_director|{self.ISSUER}|-")
        self.assertNotIn("impersonated_by", self.ok(self.ISSUER, "select data from public.events where type = 'invitation.transitioned';"))
        self.view_as_checks(inv)
        ev = self.ok(self.ISSUER, "select data from public.events where type = 'invitation.transitioned' and data -> 'transition' ->> 'key' = 'submit';")
        self.assertIn('"key": "submit"', ev)
        self.assertIn('"email": "dir@x.org"', ev)                                       # notify_submitted -> the director of the department
        self.assertIn('"template": "invitation_submitted"', ev)
        self.assertNotIn("office@x.org", ev)
        # the director: the condition hides approve_bookings (no agency), reject needs a comment
        self.fails(self.DIRECTOR, f"select public.invitation_perform_transition({inv}, 'approve_bookings');", "Transition not available: approve_bookings")
        self.fails(self.DIRECTOR, f"select public.invitation_perform_transition({inv}, 'reject');", "Comment required")
        self.fails(self.ISSUER, f"select public.invitation_perform_transition({inv}, 'approve');", "Operation not allowed")
        self.ok(self.DIRECTOR, f"select public.invitation_perform_transition({inv}, 'approve');")
        ev = self.ok(self.ISSUER, "select data from public.events where type = 'invitation.transitioned' and data -> 'transition' ->> 'key' = 'approve';")
        self.assertIn("office@x.org", ev)                                                # notify_to_manage
        self.assertIn("issuer@x.org", ev)                                                # notify_approved
        # the timed transition fires when the visit is over; the issuer and the guest are notified of the next steps
        self.assertEqual(self.system("select public.invitation_run_timed_transitions();"), "0")
        self.ok(self.OFFICE, "update public.invitations set end_date = '2020-01-13', start_date = '2020-01-10';")
        self.fails(self.OFFICE, f"select public.invitation_perform_transition({inv}, 'visit_ended');", "Automatic transition")
        self.assertEqual(self.system("select public.invitation_run_timed_transitions();"), "1")
        self.assertEqual(self.ok(self.OFFICE, "select state from public.invitations;"), "awaiting_confirmation")
        self.assertEqual(self.ok(self.OFFICE, "select count(*) from public.events where type = 'invitation.visit_ended';"), "1")
        self.assertEqual(self.ok(self.OFFICE, "select kind from public.workflow_history order by created_at desc limit 1;"), "system")
        # reminders: due after 7 days in the state, once per period
        self.assertEqual(self.ok(self.OFFICE, "select public.invitation_run_reminders();"), "0")
        self.ok(self.OFFICE, "update public.workflow_history set created_at = now() - interval '8 days';")
        self.assertEqual(self.ok(self.OFFICE, "select public.invitation_run_reminders();"), "1")
        self.assertEqual(self.ok(self.OFFICE, "select public.invitation_run_reminders();"), "0")
        ev = self.ok(self.OFFICE, "select data from public.events where type = 'invitation.reminder';")
        self.assertIn('"state": "awaiting_confirmation"', ev)
        self.assertIn('"template": "visit_confirmation_reminder"', ev)
        self.assertIn("issuer@x.org", ev)                                                # the owner of the state
        # revert: only who may, only to a state the record has been in, with a comment
        self.fails(self.ISSUER, f"select public.invitation_revert({inv}, 'in_management', 'back');", "Operation not allowed")
        self.fails(self.OFFICE, f"select public.invitation_revert({inv}, 'payment', 'back');", "State not reachable: payment")
        self.fails(self.OFFICE, f"select public.invitation_revert({inv}, 'in_management');", "Comment required")
        self.ok(self.OFFICE, f"select public.invitation_revert({inv}, 'in_management', 'bookings changed');")
        self.assertEqual(self.ok(self.OFFICE, "select state from public.invitations;"), "in_management")
        ev = self.ok(self.OFFICE, "select data from public.events where type = 'invitation.reverted';")
        self.assertIn("issuer@x.org", ev)                                                # notify_reverted
        # cancel from a running state: office only, then the record is complete
        self.ok(self.OFFICE, f"select public.invitation_perform_transition({inv}, 'cancel', 'no longer needed');")
        self.assertEqual(self.ok(self.OFFICE, "select count(*) from public.events where type = 'invitation.completed';"), "1")
        self.assertEqual(self.ok(self.OFFICE, "select public.invitation_can_edit(i) from public.invitations i;"), "f")
        # the engine is not reported as drift
        from metamodel import dbschema as D2
        found = D2.drift(meta(), D2.catalog(self.dsn), {"events", "user_roles"})
        self.assertEqual(found, [], found)
