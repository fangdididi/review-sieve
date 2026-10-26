#!/usr/bin/env python3
"""sieve.py - keep a pull request review ledger honest.

Reads one JSON ledger (see SKILL.md) and offers four commands:

  lint       check every finding for a verdict, evidence and a reply
  gate       decide CLEAR / CLEAR_WITH_NITS / KEEP_GOING / NEEDS_HUMAN
  replies    print draft replies, one per finding thread
  followups  print the real-but-out-of-scope items as a checklist

Standard library only. Exit code: 0 ok, 1 problems found, 2 bad input.
"""
import argparse
import fnmatch
import json
import sys

KINDS = ("owner", "human", "bot", "model")
SEVERITIES = ("blocker", "should", "nit")
VERDICTS = ("FIX", "WRONG", "LATER", "ASK", "STALE", "DUP")
TAGS = ("[ran]", "[read]", "[traced]")
RISKS = {"normal": 3, "sensitive": 5}
NEEDS_EVIDENCE = ("FIX", "WRONG", "STALE")
NEEDS_REPLY = ("WRONG", "LATER", "ASK")
CREEP_RATIO = 1.5
LOOP_LIMIT = 3


class LedgerError(Exception):
    pass


def load(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError as exc:
        raise LedgerError("cannot read %s: %s" % (path, exc))
    except ValueError as exc:
        raise LedgerError("not valid JSON: %s" % exc)
    if not isinstance(data, dict):
        raise LedgerError("ledger must be a JSON object")
    return data


def in_scope(path, patterns):
    if not patterns:
        return True
    return any(fnmatch.fnmatch(path, p) for p in patterns)


def lint(data):
    """Return a list of (level, code, finding_id, message)."""
    out = []
    fence = data.get("fence") or {}
    if not str(fence.get("intent", "")).strip():
        out.append(("error", "NO_INTENT", "-", "fence.intent is empty: write the one-sentence goal first"))
    risk = fence.get("risk", "normal")
    if risk not in RISKS:
        out.append(("error", "BAD_RISK", "-", "fence.risk must be normal or sensitive"))
    head = str(fence.get("head", "")).strip()
    if not head:
        out.append(("error", "NO_HEAD", "-", "fence.head (current commit) is missing"))
    scope = fence.get("in_scope") or []

    findings = data.get("findings")
    if not isinstance(findings, list):
        out.append(("error", "NO_FINDINGS", "-", "findings must be a list"))
        return out
    ids = {}
    for f in findings:
        fid = str(f.get("id", "")).strip()
        if not fid:
            out.append(("error", "NO_ID", "?", "a finding has no id"))
            continue
        if fid in ids:
            out.append(("error", "DUP_ID", fid, "id used twice"))
        ids[fid] = f
    for fid, f in ids.items():
        kind = f.get("kind")
        sev = f.get("severity")
        verdict = f.get("verdict")
        ev = str(f.get("evidence", "")).strip()
        reply = str(f.get("reply", "")).strip()
        if kind not in KINDS:
            out.append(("error", "BAD_KIND", fid, "kind must be one of " + "/".join(KINDS)))
        if sev not in SEVERITIES:
            out.append(("error", "BAD_SEVERITY", fid, "severity must be blocker/should/nit"))
        if not str(f.get("claim", "")).strip():
            out.append(("error", "NO_CLAIM", fid, "write what the reviewer says is wrong"))
        if verdict is None:
            out.append(("info", "PENDING", fid, "no verdict yet"))
            continue
        if verdict not in VERDICTS:
            out.append(("error", "BAD_VERDICT", fid, "verdict must be one of " + "/".join(VERDICTS)))
            continue
        if verdict in NEEDS_EVIDENCE and not any(ev.startswith(t) for t in TAGS):
            out.append(("error", "NO_EVIDENCE", fid, verdict + " needs evidence starting with [ran], [read] or [traced]"))
        if verdict in NEEDS_REPLY and not reply:
            out.append(("error", "NO_REPLY", fid, verdict + " needs a written reply on the thread"))
        if verdict == "DUP":
            target = ids.get(str(f.get("dup_of", "")))
            if target is None:
                out.append(("error", "DUP_TARGET", fid, "dup_of must name another finding id"))
            elif target.get("verdict") == "DUP" or target is f:
                out.append(("error", "DUP_CHAIN", fid, "dup_of must point at a finding that is not itself a duplicate"))
        if kind == "owner" and verdict in ("WRONG", "LATER"):
            out.append(("error", "OWNER_OVERRULE", fid, "do not decline the owner's own comment; mark it ASK and talk to them"))
        if verdict == "FIX" and f.get("path") and not in_scope(f["path"], scope):
            out.append(("warn", "SCOPE_ESCAPE", fid, "fix touches %s, outside the fence" % f["path"]))
        made_on = str(f.get("made_on", "")).strip()
        if head and made_on and not head.startswith(made_on) and not made_on.startswith(head):
            if verdict not in ("STALE", "DUP", "LATER") and head[:7] not in ev:
                out.append(("warn", "OLD_HEAD", fid, "raised on %s; re-check it on %s and cite that sha in evidence" % (made_on, head[:7])))
        try:
            raised = int(f.get("raised", 1))
        except (TypeError, ValueError):
            raised = 1
        if verdict == "WRONG" and raised >= LOOP_LIMIT:
            out.append(("warn", "LOOPING", fid, "declined %d times and raised again: hand it to a human" % raised))
    return out


def gate(data):
    """Return (verdict, reasons, stats)."""
    issues = lint(data)
    errors = [i for i in issues if i[0] == "error"]
    findings = [f for f in data.get("findings") or [] if isinstance(f, dict)]
    fence = data.get("fence") or {}
    budget = RISKS.get(fence.get("risk", "normal"), 3)
    rounds = data.get("rounds") or []
    used = len(rounds)
    pending = [f for f in findings if f.get("verdict") is None]
    serious_pending = [f for f in pending if f.get("severity") in ("blocker", "should")]
    asks = [f for f in findings if f.get("verdict") == "ASK"]
    looping = [i for i in issues if i[1] == "LOOPING"]
    reasons = []
    stats = {
        "findings": len(findings),
        "pending": len(pending),
        "rounds_used": used,
        "round_budget": budget,
    }
    counts = {}
    for f in findings:
        v = f.get("verdict") or "PENDING"
        counts[v] = counts.get(v, 0) + 1
    stats["by_verdict"] = counts
    sizes = [r.get("diff_lines") for r in rounds if isinstance(r.get("diff_lines"), int)]
    if len(sizes) >= 2 and sizes[0] > 0:
        ratio = sizes[-1] / float(sizes[0])
        stats["growth"] = round(ratio, 2)
        if ratio > CREEP_RATIO:
            reasons.append("diff grew %.1fx since round 1: look for fixes that could be declined or narrowed" % ratio)
    if errors:
        reasons.extend("%s %s: %s" % (e[1], e[2], e[3]) for e in errors)
        return "NEEDS_HUMAN" if any(e[1] == "OWNER_OVERRULE" for e in errors) else "KEEP_GOING", reasons, stats
    if asks:
        reasons.append("waiting on a person for: " + ", ".join(f["id"] for f in asks))
    if looping:
        reasons.append("same finding keeps coming back: " + ", ".join(i[2] for i in looping))
    if asks or looping:
        return "NEEDS_HUMAN", reasons, stats
    if serious_pending:
        ids = ", ".join(f["id"] for f in serious_pending)
        if used >= budget:
            reasons.append("round budget spent (%d/%d) with open blocker/should: %s" % (used, budget, ids))
            return "NEEDS_HUMAN", reasons, stats
        reasons.append("open blocker/should: " + ids)
        return "KEEP_GOING", reasons, stats
    unposted = [f["id"] for f in findings if f.get("verdict") in NEEDS_REPLY and not f.get("posted")]
    if unposted:
        reasons.append("replies written but not posted yet: " + ", ".join(unposted))
        return "KEEP_GOING", reasons, stats
    if pending:
        reasons.append("only nits left (%d): decline or fix them without another review round" % len(pending))
        return "CLEAR_WITH_NITS", reasons, stats
    reasons.append("every finding has a verdict and evidence")
    return "CLEAR", reasons, stats


OPENERS = {
    "FIX": "Fixed in {commit}.",
    "WRONG": "Not changing this.",
    "LATER": "Real, but outside this PR.",
    "ASK": "Need your call before I touch this.",
    "STALE": "No longer applies on {head}.",
    "DUP": "Same issue as {dup_of}; handled there.",
}


def replies(data, note=None):
    fence = data.get("fence") or {}
    head = str(fence.get("head", ""))[:7]
    blocks = []
    for f in data.get("findings") or []:
        v = f.get("verdict")
        if v is None:
            continue
        where = f.get("path", "")
        if where and f.get("line"):
            where += ":%s" % f["line"]
        opener = OPENERS.get(v, "").format(commit=f.get("commit", "<commit>"), head=head or "<head>", dup_of=f.get("dup_of", "?"))
        body = str(f.get("reply", "")).strip()
        ev = str(f.get("evidence", "")).strip()
        lines = ["### %s (%s) %s" % (f.get("id"), f.get("source", f.get("kind", "?")), where)]
        if note:
            lines.append("> [!NOTE]")
            lines.append("> " + note)
            lines.append("")
        lines.append(opener + (" " + body if body else ""))
        if ev and v in NEEDS_EVIDENCE:
            lines.append("")
            lines.append("Evidence: " + ev)
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def followups(data):
    rows = []
    for f in data.get("findings") or []:
        if f.get("verdict") == "LATER":
            where = (" (%s)" % f["path"]) if f.get("path") else ""
            rows.append("- [ ] %s%s: %s" % (f.get("id"), where, str(f.get("claim", "")).strip()))
    return "\n".join(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Review ledger checker")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("lint", "gate", "replies", "followups"):
        p = sub.add_parser(name)
        p.add_argument("ledger")
        if name == "gate":
            p.add_argument("--json", action="store_true")
        if name == "replies":
            p.add_argument("--note", help="callout line, e.g. 'Agent reply written for @me'")
    args = ap.parse_args(argv)
    try:
        data = load(args.ledger)
    except LedgerError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    if args.cmd == "lint":
        issues = lint(data)
        for level, code, fid, msg in issues:
            print("%-5s %-14s %-6s %s" % (level.upper(), code, fid, msg))
        errors = sum(1 for i in issues if i[0] == "error")
        print("%d error(s), %d warning(s), %d pending" % (
            errors, sum(1 for i in issues if i[0] == "warn"), sum(1 for i in issues if i[1] == "PENDING")))
        return 1 if errors else 0
    if args.cmd == "gate":
        verdict, reasons, stats = gate(data)
        if args.json:
            print(json.dumps({"verdict": verdict, "reasons": reasons, "stats": stats}, ensure_ascii=False, indent=1))
        else:
            print(verdict)
            for r in reasons:
                print("  - " + r)
            print("  rounds %d/%d, findings %d, pending %d" % (
                stats["rounds_used"], stats["round_budget"], stats["findings"], stats["pending"]))
        return 0 if verdict in ("CLEAR", "CLEAR_WITH_NITS") else 1
    if args.cmd == "replies":
        print(replies(data, args.note))
        return 0
    if args.cmd == "followups":
        text = followups(data)
        print(text if text else "(no follow-ups)")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
