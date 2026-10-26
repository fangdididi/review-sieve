import copy
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import sieve  # noqa: E402

BASE = {
    "fence": {"intent": "Stop dropping 503s.", "in_scope": ["src/*"], "risk": "normal", "head": "abc1234"},
    "rounds": [{"n": 1, "head": "abc1234", "diff_lines": 100}],
    "findings": [],
}


def ledger(*findings, **fence):
    d = copy.deepcopy(BASE)
    d["fence"].update(fence)
    d["findings"] = [dict(f) for f in findings]
    return d


def finding(**kw):
    f = {"id": "F1", "kind": "bot", "severity": "should", "claim": "bug here",
         "made_on": "abc1234", "path": "src/a.py"}
    f.update(kw)
    return f


def codes(data):
    return [i[1] for i in sieve.lint(data)]


class LintFence(unittest.TestCase):
    def test_clean_fence_no_errors(self):
        self.assertEqual(codes(ledger()), [])

    def test_missing_intent(self):
        self.assertIn("NO_INTENT", codes(ledger(intent="  ")))

    def test_bad_risk(self):
        self.assertIn("BAD_RISK", codes(ledger(risk="high")))

    def test_missing_head(self):
        self.assertIn("NO_HEAD", codes(ledger(head="")))

    def test_findings_not_list(self):
        d = ledger()
        d["findings"] = {}
        self.assertIn("NO_FINDINGS", codes(d))


class LintFindings(unittest.TestCase):
    def test_pending_is_info(self):
        issues = sieve.lint(ledger(finding()))
        self.assertEqual([(i[0], i[1]) for i in issues], [("info", "PENDING")])

    def test_no_id(self):
        self.assertIn("NO_ID", codes(ledger(finding(id=""))))

    def test_duplicate_id(self):
        self.assertIn("DUP_ID", codes(ledger(finding(), finding())))

    def test_bad_kind(self):
        self.assertIn("BAD_KIND", codes(ledger(finding(kind="robot"))))

    def test_bad_severity(self):
        self.assertIn("BAD_SEVERITY", codes(ledger(finding(severity="major"))))

    def test_no_claim(self):
        self.assertIn("NO_CLAIM", codes(ledger(finding(claim=""))))

    def test_bad_verdict(self):
        self.assertIn("BAD_VERDICT", codes(ledger(finding(verdict="MAYBE"))))

    def test_fix_without_evidence(self):
        self.assertIn("NO_EVIDENCE", codes(ledger(finding(verdict="FIX"))))

    def test_fix_with_untagged_evidence(self):
        self.assertIn("NO_EVIDENCE", codes(ledger(finding(verdict="FIX", evidence="looks fine"))))

    def test_fix_with_ran_evidence_ok(self):
        self.assertEqual(codes(ledger(finding(verdict="FIX", evidence="[ran] test passes"))), [])

    def test_each_tag_accepted(self):
        for tag in sieve.TAGS:
            self.assertEqual(codes(ledger(finding(verdict="STALE", evidence=tag + " gone"))), [], tag)

    def test_wrong_needs_reply(self):
        c = codes(ledger(finding(verdict="WRONG", evidence="[read] x")))
        self.assertIn("NO_REPLY", c)

    def test_later_needs_reply_not_evidence(self):
        c = codes(ledger(finding(verdict="LATER")))
        self.assertIn("NO_REPLY", c)
        self.assertNotIn("NO_EVIDENCE", c)

    def test_ask_needs_reply(self):
        self.assertIn("NO_REPLY", codes(ledger(finding(verdict="ASK"))))

    def test_dup_target_missing(self):
        self.assertIn("DUP_TARGET", codes(ledger(finding(verdict="DUP", dup_of="F9"))))

    def test_dup_chain(self):
        a = finding(id="F1", verdict="DUP", dup_of="F2")
        b = finding(id="F2", verdict="DUP", dup_of="F3")
        c = finding(id="F3", verdict="FIX", evidence="[ran] ok")
        self.assertIn("DUP_CHAIN", codes(ledger(a, b, c)))

    def test_dup_self(self):
        self.assertIn("DUP_CHAIN", codes(ledger(finding(verdict="DUP", dup_of="F1"))))

    def test_dup_ok(self):
        a = finding(id="F1", verdict="FIX", evidence="[ran] ok")
        b = finding(id="F2", verdict="DUP", dup_of="F1")
        self.assertEqual(codes(ledger(a, b)), [])

    def test_owner_cannot_be_declined(self):
        for v in ("WRONG", "LATER"):
            c = codes(ledger(finding(kind="owner", verdict=v, evidence="[read] x", reply="no")))
            self.assertIn("OWNER_OVERRULE", c, v)

    def test_owner_ask_is_fine(self):
        self.assertEqual(codes(ledger(finding(kind="owner", verdict="ASK", reply="which way?"))), [])

    def test_scope_escape(self):
        c = codes(ledger(finding(verdict="FIX", evidence="[ran] ok", path="lib/other.py")))
        self.assertIn("SCOPE_ESCAPE", c)

    def test_empty_scope_means_anywhere(self):
        c = codes(ledger(finding(verdict="FIX", evidence="[ran] ok", path="lib/other.py"), in_scope=[]))
        self.assertNotIn("SCOPE_ESCAPE", c)

    def test_old_head_warns(self):
        c = codes(ledger(finding(verdict="FIX", evidence="[ran] ok", made_on="0000000")))
        self.assertIn("OLD_HEAD", c)

    def test_old_head_cleared_by_citing_head(self):
        c = codes(ledger(finding(verdict="FIX", evidence="[ran] ok on abc1234", made_on="0000000")))
        self.assertNotIn("OLD_HEAD", c)

    def test_old_head_skipped_for_stale_and_later(self):
        c1 = codes(ledger(finding(verdict="STALE", evidence="[read] gone", made_on="0000000")))
        c2 = codes(ledger(finding(verdict="LATER", reply="later", made_on="0000000")))
        self.assertNotIn("OLD_HEAD", c1)
        self.assertNotIn("OLD_HEAD", c2)

    def test_short_sha_matches_long_head(self):
        c = codes(ledger(finding(verdict="FIX", evidence="[ran] ok", made_on="abc1234"), head="abc1234deadbeef"))
        self.assertNotIn("OLD_HEAD", c)

    def test_looping(self):
        c = codes(ledger(finding(verdict="WRONG", evidence="[read] x", reply="no", raised=3)))
        self.assertIn("LOOPING", c)

    def test_bad_raised_value_tolerated(self):
        c = codes(ledger(finding(verdict="WRONG", evidence="[read] x", reply="no", raised="lots")))
        self.assertNotIn("LOOPING", c)


class Gate(unittest.TestCase):
    def v(self, data):
        return sieve.gate(data)[0]

    def test_empty_is_clear(self):
        self.assertEqual(self.v(ledger()), "CLEAR")

    def test_errors_keep_going(self):
        self.assertEqual(self.v(ledger(finding(verdict="FIX"))), "KEEP_GOING")

    def test_owner_overrule_needs_human(self):
        f = finding(kind="owner", verdict="WRONG", evidence="[read] x", reply="no")
        self.assertEqual(self.v(ledger(f)), "NEEDS_HUMAN")

    def test_ask_needs_human(self):
        self.assertEqual(self.v(ledger(finding(verdict="ASK", reply="?"))), "NEEDS_HUMAN")

    def test_looping_needs_human(self):
        f = finding(verdict="WRONG", evidence="[read] x", reply="no", raised=4, posted=True)
        self.assertEqual(self.v(ledger(f)), "NEEDS_HUMAN")

    def test_open_should_keeps_going(self):
        self.assertEqual(self.v(ledger(finding())), "KEEP_GOING")

    def test_budget_spent_needs_human(self):
        d = ledger(finding(severity="blocker"))
        d["rounds"] = [{"n": i} for i in range(1, 4)]
        self.assertEqual(self.v(d), "NEEDS_HUMAN")

    def test_sensitive_budget_is_five(self):
        d = ledger(finding(severity="blocker"), risk="sensitive")
        d["rounds"] = [{"n": i} for i in range(1, 4)]
        self.assertEqual(self.v(d), "KEEP_GOING")
        self.assertEqual(sieve.gate(d)[2]["round_budget"], 5)

    def test_only_nits(self):
        self.assertEqual(self.v(ledger(finding(severity="nit"))), "CLEAR_WITH_NITS")

    def test_unposted_reply_blocks_clear(self):
        f = finding(verdict="WRONG", evidence="[read] x", reply="no")
        self.assertEqual(self.v(ledger(f)), "KEEP_GOING")
        f["posted"] = True
        self.assertEqual(self.v(ledger(f)), "CLEAR")

    def test_creep_reason(self):
        d = ledger()
        d["rounds"] = [{"n": 1, "diff_lines": 100}, {"n": 2, "diff_lines": 200}]
        verdict, reasons, stats = sieve.gate(d)
        self.assertEqual(stats["growth"], 2.0)
        self.assertTrue(any("grew" in r for r in reasons))

    def test_no_creep_under_ratio(self):
        d = ledger()
        d["rounds"] = [{"n": 1, "diff_lines": 100}, {"n": 2, "diff_lines": 140}]
        self.assertFalse(any("grew" in r for r in sieve.gate(d)[1]))

    def test_counts_by_verdict(self):
        d = ledger(finding(id="A", verdict="FIX", evidence="[ran] ok"), finding(id="B"))
        self.assertEqual(sieve.gate(d)[2]["by_verdict"], {"FIX": 1, "PENDING": 1})


class Output(unittest.TestCase):
    def test_replies_lead_with_verdict(self):
        f = finding(verdict="FIX", evidence="[ran] ok", commit="beef123", reply="Narrowed the check.", line=4)
        text = sieve.replies(ledger(f))
        self.assertIn("Fixed in beef123. Narrowed the check.", text)
        self.assertIn("src/a.py:4", text)
        self.assertIn("Evidence: [ran] ok", text)

    def test_replies_skip_pending(self):
        self.assertEqual(sieve.replies(ledger(finding())), "")

    def test_replies_note(self):
        f = finding(verdict="ASK", reply="Which way?")
        text = sieve.replies(ledger(f), note="Agent reply for @me")
        self.assertIn("> [!NOTE]\n> Agent reply for @me", text)

    def test_dup_reply_names_target(self):
        a = finding(id="F1", verdict="FIX", evidence="[ran] ok")
        b = finding(id="F2", verdict="DUP", dup_of="F1")
        self.assertIn("Same issue as F1", sieve.replies(ledger(a, b)))

    def test_followups(self):
        f = finding(verdict="LATER", reply="later", claim="cache grows")
        self.assertEqual(sieve.followups(ledger(f)), "- [ ] F1 (src/a.py): cache grows")


class Cli(unittest.TestCase):
    def run_cli(self, data, *args):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
            if isinstance(data, str):
                fh.write(data)
            else:
                json.dump(data, fh)
        out, err = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(out), redirect_stderr(err):
                code = sieve.main(list(args[:1]) + [fh.name] + list(args[1:]))
        finally:
            os.unlink(fh.name)
        return code, out.getvalue(), err.getvalue()

    def test_bad_json_exit_2(self):
        self.assertEqual(self.run_cli("{oops", "lint")[0], 2)

    def test_non_object_exit_2(self):
        self.assertEqual(self.run_cli("[]", "gate")[0], 2)

    def test_lint_exit_codes(self):
        self.assertEqual(self.run_cli(ledger(), "lint")[0], 0)
        self.assertEqual(self.run_cli(ledger(finding(verdict="FIX")), "lint")[0], 1)

    def test_gate_json(self):
        code, out, _ = self.run_cli(ledger(), "gate", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["verdict"], "CLEAR")

    def test_followups_empty(self):
        self.assertIn("(no follow-ups)", self.run_cli(ledger(), "followups")[1])

    def test_examples(self):
        en = os.path.join(ROOT, "examples", "retry-backoff.ledger.json")
        zh = os.path.join(ROOT, "examples", "coupon-reminder.zh.ledger.json")
        self.assertEqual(sieve.gate(sieve.load(en))[0], "CLEAR_WITH_NITS")
        self.assertEqual(sieve.gate(sieve.load(zh))[0], "NEEDS_HUMAN")


if __name__ == "__main__":
    unittest.main()
