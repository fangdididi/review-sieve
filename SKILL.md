---
name: review-sieve
description: Use when a pull request has collected review findings from bots, other AI models, teammates or the repo owner and you need to decide what to fix, what to decline with a reason, and when to stop. Turns a pile of comments into a ledger where every finding gets a verdict backed by evidence, keeps the PR inside a scope fence, caps review rounds, and writes the thread replies.
---

# Review Sieve

[中文版](SKILL.zh-CN.md)

## What this is

A pull request today often gets reviewed by several voices at once: one or two
review bots, a second or third AI model you asked for a review, a teammate, and
the person who owns the work. Together they leave more comments than anyone
can take on faith. Some are real bugs. Some were true on an older commit and
are already gone. Several are the same point in different words. Some are
correct but belong to a different PR. A few are simply wrong.

Two failure modes show up again and again:

- **Yes to everything.** Every suggestion gets applied, the PR doubles in
  size, new bugs come in with the "fixes", and review never ends.
- **No to everything.** Comments are waved away or resolved without a reply,
  and a real bug ships.

Review Sieve is a short, strict routine that sits between the comments and
your keyboard. Every finding goes into one ledger file. Nothing gets changed
until the finding has a verdict, and no verdict counts without evidence you
produced yourself on the current commit. The PR has a written fence, a fixed
number of review rounds, and a clear finish line.

## When to use it

- A PR has comments from more than one reviewer, or from any bot.
- You asked several models to review the same change and they disagree.
- You picked up a PR someone else started and inherited its open threads.
- A review loop has gone on for more than two rounds and the diff keeps
  growing.
- You are an agent answering review comments on someone's behalf.

Skip it for a one-line PR with a single "LGTM".

## The ledger

Keep one JSON file next to your work, for example `.review/ledger.json`. It
has three parts.

```json
{
  "fence": {
    "intent": "One sentence: what this PR changes for whom.",
    "in_scope": ["src/webhooks/*", "tests/webhooks/*"],
    "out_of_scope": ["the admin UI", "other HTTP clients"],
    "risk": "normal",
    "head": "9f2c41e",
    "owner": "@you"
  },
  "rounds": [{"n": 1, "head": "4b7d0aa", "diff_lines": 140}],
  "findings": [
    {"id": "F1", "kind": "bot", "source": "review-bot", "made_on": "4b7d0aa",
     "path": "src/webhooks/deliver.py", "line": 58, "severity": "blocker",
     "claim": "Retries also fire on 400.",
     "verdict": "FIX", "commit": "9f2c41e",
     "evidence": "[ran] test_no_retry_on_4xx failed before, passes on 9f2c41e",
     "reply": "Only 429 and 5xx retry now.", "posted": true}
  ]
}
```

Field meanings:

| Field | Meaning |
|---|---|
| `kind` | `owner` (the person whose PR or decision it is), `human`, `bot`, `model` |
| `severity` | `blocker` (wrong result, data loss, security), `should` (real problem, not urgent), `nit` (taste, naming, style) |
| `made_on` | the commit the reviewer was looking at |
| `verdict` | one of the six below, or absent while still open |
| `evidence` | starts with `[ran]`, `[read]` or `[traced]` |
| `raised` | how many times this same point has been raised |
| `posted` | `true` once the reply is actually on the thread |

### The six verdicts

| Verdict | Use when | Needs |
|---|---|---|
| `FIX` | You confirmed the problem on the current head, and it is inside the fence | evidence, a commit |
| `WRONG` | You checked and the claim does not hold for this code | evidence, a reply |
| `LATER` | Real, but outside the fence | a reply, a follow-up item |
| `ASK` | Unclear, or it would reverse something the owner decided | a reply with a concrete question |
| `STALE` | Was true on an older commit, gone on the current head | evidence |
| `DUP` | Same point as another finding | `dup_of` naming a finding that is not itself a duplicate |

Evidence tags mean what they say. `[ran]` is a command, test or reproduction
you ran and watched. `[read]` is code you opened at the current head, cited
with file and line. `[traced]` is following callers or data flow far enough to
answer the question. A reviewer's confidence, the number of reviewers who
agree, and "probably fine" are not evidence.

## Steps

### 1. Write the fence before you read a single comment

Write `fence.intent` as one plain sentence about the change's effect, not its
mechanics. List the paths the PR is meant to touch and two or three things it
deliberately does not do. Set `risk` to `sensitive` if the change touches
authentication, permissions, money, data deletion, migrations or concurrency;
otherwise `normal`. Record the current head commit.

Writing this first matters: once the comments are in front of you, every one
of them will feel in scope.

### 2. Take every finding in, unedited in meaning

Add one row per comment, from every source, including the ones you suspect are
wrong. Restate the claim in one sentence in your own words. If you cannot
restate it, that is already a sign it will end as `ASK`. Note which commit the
reviewer saw. Assign severity by consequence, not by the reviewer's label: a
bot that marks everything "critical" does not make a rename a blocker.

### 3. Collapse duplicates and drop the stale

Group findings that point at the same lines and the same concern. Keep the
clearest one, mark the rest `DUP` with `dup_of`. Agreement between three bots
is a reason to look first, not a reason to believe.

For anything raised on an older commit, open the code at the current head. If
the problem is gone, mark `STALE` with `[read]` evidence. If it is still
there, cite the current head's sha in your evidence when you decide.

### 4. Verify, one finding at a time

Pick the probe that settles the question fastest:

- a claim about behaviour: write or run a test that would fail if the claim
  is true (`[ran]`);
- a claim about a specific line: read it at the current head and quote the
  relevant part (`[read]`);
- a claim about who calls something or where data goes: trace it (`[traced]`).

Then choose the verdict. Two hard rules:

- **The owner is never declined by you.** If the owner's comment conflicts
  with your judgment, mark it `ASK`, explain what you found, and offer a
  concrete option. The owner decides.
- **Repeated is not right, and also not ignorable.** If a point you declined
  with evidence comes back a third time, stop arguing and hand it to a person.

### 5. Fix with the smallest change that makes the evidence pass

For each `FIX`, change only what the finding needs. Prefer the fix that
deletes or narrows code over one that adds a new layer. Run the probe again
and record the passing result and commit. If the fix needs files outside
`in_scope`, either the fence was wrong (update it on purpose and say why) or
the finding is really `LATER`.

### 6. Write the replies

Every `WRONG`, `LATER` and `ASK` gets a written reply before the thread is
resolved. Lead with the conclusion, then the reason, then the evidence.
No thanks-padding, no apologies, no status narration.

- `FIX`: "Fixed in `9f2c41e`. Only 429 and 5xx retry now." plus the test.
- `WRONG`: "Not changing this. The session is owned by one worker and never
  shared across threads (see `worker.py` `run_loop`)."
- `LATER`: "Real, but outside this PR. Opened as a follow-up."
- `ASK`: a question that can be answered in one line.

If you are an agent replying on someone's behalf, mark the reply as
agent-written at the top so readers know who is speaking. Check every reply
for secrets and private details before posting. Set `posted: true` only after
the platform confirms the comment exists, and resolve the thread only after
that.

### 7. Count rounds and decide whether to stop

A round is one full pass of review on one head. Add a row to `rounds` with
the head and the size of the diff (added plus removed lines) each time.

- Budget: 3 rounds for `normal`, 5 for `sensitive`.
- A round that brings no new blocker or should ends the loop. Nits do not buy
  another round.
- If the diff has grown more than 1.5x since round 1, re-read your `FIX`
  items: some of them are probably `LATER`.

Run the gate:

```bash
python3 scripts/sieve.py lint .review/ledger.json
python3 scripts/sieve.py gate .review/ledger.json
```

| Gate | Meaning |
|---|---|
| `CLEAR` | every finding has a verdict, evidence and a posted reply |
| `CLEAR_WITH_NITS` | only nits are open; handle them without another round |
| `KEEP_GOING` | an open blocker/should, a ledger error, or an unposted reply |
| `NEEDS_HUMAN` | an `ASK`, a looping finding, an attempt to decline the owner, or the round budget is spent with serious items open |

### 8. Close out

Print the follow-ups and put them where the team tracks work:

```bash
python3 scripts/sieve.py followups .review/ledger.json
python3 scripts/sieve.py replies --note "🤖 Agent reply written for @you" .review/ledger.json
```

Report in this order: the gate result, what was fixed (with proof), what was
declined and why, what is waiting on a person, and the follow-up list.

## Example

`examples/retry-backoff.ledger.json` is a webhook retry PR with six findings:
a real blocker from a bot (`FIX`, with a failing-then-passing test), a jitter
suggestion from a second model (`FIX`), a thread-safety false positive
(`WRONG`, traced to a single-worker loop), a teammate pointing out the same bug
in another client (`LATER`), a third model repeating the blocker (`DUP`), and a
rename nit left open. The gate says `CLEAR_WITH_NITS`.

`examples/coupon-reminder.zh.ledger.json` (Chinese) is a sensitive PR in its
third round. The owner asked for a time-zone change that the data cannot fully
support (`ASK`), a bot keeps re-raising a point already disproven (`raised: 3`),
and the diff has grown 2.2x. The gate says `NEEDS_HUMAN`.

## Tips

- Read the whole set of comments once before verifying any. Findings are often
  linked, and fixing one can make two others stale.
- Run the checks the PR already has before round 1, so you know which
  failures were there before you.
- Keep declined nits out of new rounds. A rename never needs a fresh review.
- When two reviewers contradict each other, the code decides; write the probe
  that tells them apart.
- Do not write your own polling loop to wait for bots. Use the platform's
  watcher or check back when the next event arrives.
- A `LATER` without a tracked follow-up is a `WRONG` in disguise.
