# Review Sieve

**English** | [简体中文](README.zh-CN.md)

An agent skill for answering pull request review the honest way. When a PR has
comments from review bots, extra AI models, teammates and the owner all at
once, Review Sieve turns them into one ledger where every finding gets a
verdict backed by evidence you produced on the current commit, keeps the PR
inside a written scope fence, caps the number of review rounds, and drafts the
thread replies.

Works with Claude Code, Codex, Cursor and any agent that can read a
`SKILL.md`. The helper script is plain Python 3 with no dependencies.

## The problem

Multi-reviewer PRs fail in two ways. Either every suggestion is applied, the
diff doubles and review never ends, or comments are dismissed without a
reason and a real bug ships. Neither is a reviewing problem; both are a
*receiving* problem. This skill is about receiving review well.

## Features

- **Scope fence first.** One-sentence intent, in-scope paths, explicit
  non-goals and a risk level, written before any comment is read.
- **Six verdicts.** `FIX`, `WRONG`, `LATER`, `ASK`, `STALE`, `DUP`, each with
  its own required proof.
- **Evidence tags.** `[ran]`, `[read]`, `[traced]`. Reviewer confidence and
  reviewer headcount never count as evidence.
- **Stale check.** Findings raised on an older commit must be re-checked on
  the current head.
- **Owner guard.** The owner's own comment is never declined by the agent; it
  becomes a concrete question instead.
- **Loop breaker.** A point declined with evidence that comes back a third
  time goes to a person.
- **Round budget and creep meter.** 3 rounds (5 for sensitive changes), nits
  never buy a new round, and a warning when the diff grows past 1.5x.
- **Reply drafts and follow-ups.** Verdict-first replies, an optional
  agent-written notice, and a checklist of out-of-scope items.

## Installation

Copy the folder into your agent's skills directory.

```bash
git clone https://github.com/fangdididi/review-sieve
# Claude Code
cp -R review-sieve ~/.claude/skills/review-sieve
# Codex
cp -R review-sieve ~/.codex/skills/review-sieve
# Cursor (project skill)
mkdir -p .cursor/skills && cp -R review-sieve .cursor/skills/review-sieve
```

Other agents: point them at `SKILL.md` (or `SKILL.zh-CN.md`) and keep the
`scripts/` folder next to it.

## Usage

Ask your agent something like:

> "This PR has 14 review comments from two bots and Dana. Run review sieve on
> it."

The agent writes `.review/ledger.json`, verifies findings one by one, fixes
what is real and in scope, drafts replies, and stops when the gate says so.
You can run the checks yourself:

```bash
python3 scripts/sieve.py lint .review/ledger.json       # missing verdicts, evidence, replies
python3 scripts/sieve.py gate .review/ledger.json       # CLEAR / CLEAR_WITH_NITS / KEEP_GOING / NEEDS_HUMAN
python3 scripts/sieve.py gate --json .review/ledger.json
python3 scripts/sieve.py replies --note "🤖 Agent reply written for @you" .review/ledger.json
python3 scripts/sieve.py followups .review/ledger.json
```

Exit codes: `0` ok, `1` problems found (or gate not clear), `2` unreadable
ledger.

## Examples

```text
$ python3 scripts/sieve.py gate examples/retry-backoff.ledger.json
CLEAR_WITH_NITS
  - only nits left (1): decline or fix them without another review round
  rounds 2/3, findings 6, pending 1

$ python3 scripts/sieve.py gate examples/coupon-reminder.zh.ledger.json
NEEDS_HUMAN
  - diff grew 2.2x since round 1: look for fixes that could be declined or narrowed
  - waiting on a person for: Z2
  - same finding keeps coming back: Z4
  rounds 3/5, findings 4, pending 0
```

- `examples/retry-backoff.ledger.json`: webhook retries, six findings covering
  a real blocker, a false positive, an out-of-scope bug, a duplicate and a nit.
- `examples/coupon-reminder.zh.ledger.json` (Chinese): a sensitive PR in round
  three with an open question for the owner, a looping bot finding and scope
  creep.

## File structure

```text
review-sieve/
├── SKILL.md                 # skill instructions (English)
├── SKILL.zh-CN.md           # skill instructions (Chinese)
├── README.md                # this file
├── README.zh-CN.md          # Chinese README
├── LICENSE                  # MIT
├── scripts/
│   └── sieve.py             # lint / gate / replies / followups
├── examples/
│   ├── retry-backoff.ledger.json
│   └── coupon-reminder.zh.ledger.json
└── tests/
    └── test_sieve.py        # 57 tests: python3 -m unittest discover -s tests
```

## License

MIT © fangdididi
