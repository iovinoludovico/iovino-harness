"""The behaviour model (behavior.yaml) checked against the domain metamodel: expressions, principals,
workflows, derivations, events, reactions, subscriptions; the CLI and the hook that run the check.

python3 -m unittest discover -s plugins/modeler/tests
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from metamodel import behavior as B  # noqa: E402
from metamodel import cli  # noqa: E402
from metamodel import core as M  # noqa: E402
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
        self.fails("reason = guest", "a reference cannot be compared")
        self.fails("invitationFunds = 3", "a collection cannot be compared")
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
        node, _ = self.check("state = 'it''s'".replace("''", "\\'"))
        self.assertEqual(X.to_text(X.parse(X.to_text(node))), X.to_text(node))


class BehaviorTests(unittest.TestCase):
    def test_fixture_is_valid(self):
        rep = B.validate(behavior(), meta())
        self.assertEqual(rep.errors, [])
        # derived attributes still computed in code are reported, not refused
        self.assertEqual(sorted(w.split(":")[0] for w in rep.warnings),
                         ["derivations.Invitation.accommodationPerNight", "derivations.Invitation.compensationAmount",
                          "derivations.Invitation.mealsPerDay", "derivations.Invitation.totalAmount"])
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
            (root / "behavior.yaml").write_text(BEHAVIOR.read_text())
            code, out, _ = self.run_cli("validate", str(root / "domain.ecore.yaml"))
            self.assertEqual(code, 0)
            self.assertIn("--- behavior.yaml against the metamodel", out)
            self.assertIn("WARNING derivations.Invitation.totalAmount", out)
            code, out, _ = self.run_cli("validate", str(root / "domain.ecore.yaml"), "--json")
            data = json.loads(out)
            self.assertTrue(data["ok"] and data["behavior"]["ok"])
            self.assertEqual(len(data["behavior"]["warnings"]), 4)
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
            self.assertIn("WARNING derivations.Invitation.totalAmount", out.stdout)
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
