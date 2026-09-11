# Autonomous Execution Log

Decisions and blockers hit while executing Phases 2-5 autonomously (no user check-ins),
per instruction given 2026-09-10. Each entry: phase, what was ambiguous, the option chosen,
the alternatives considered, and why. `[DECISION]` = a judgment call made to keep moving.
`[BLOCKER]` = something had to be stubbed, skipped, or deferred because it could not be
resolved autonomously.

---

## [BLOCKER] Phase 1 has no recoverable planning-artifact trail in this repo

**Phase:** 1 — Sanitization & Repo Foundation

**What was ambiguous/blocking:** `.planning/ROADMAP.md` and `STATE.md` both assert Phase 1
is complete (4/4 plans, "completed 2026-09-10"), but `.planning/phases/01-*/` does not exist
in this repo — no PLAN.md, SUMMARY.md, CONTEXT.md, RESEARCH.md, or VERIFICATION.md. Per
STATE.md's own decision log, Phase 1 was executed in a separate reference repo
("seinäjoki_hotel"); only ROADMAP.md/REQUIREMENTS.md/STATE.md/config.json were copied over
when this repo was bootstrapped — the phase's artifact trail was deliberately left behind.
As a result `gsd_run query init.manager` correctly reports `phase_complete: false` /
`verification_status: missing` for Phase 1, and the autonomous workflow's phase-discovery
step would treat it as an incomplete phase requiring discuss→plan→execute.

**Option chosen:** Verified Phase 1's four ROADMAP success criteria directly against the
live, git-tracked codebase (fresh git init with no remote/shared ancestry; a real-client
marker scan via `scripts/scan_for_real_client_trace.sh $(git ls-files)` returning clean;
full test suite green, 68/68; "Hotelli Frami" branding confirmed present). Wrote this
evidence into a retroactive `01-VERIFICATION.md` (status: passed). Then **excluded Phase 1
from the autonomous run's phase queue** (equivalent to `--from 2`) rather than letting the
tooling's stale-verification flag route it into automated re-planning/re-execution.

**Alternatives considered:**
1. Fabricate `01-PLAN.md`/`01-SUMMARY.md` files to satisfy the tooling's artifact checks —
   rejected: inventing a plan/execution history that never happened in this repo is
   dishonest record-keeping and could mislead future audits.
2. Let the autonomous pipeline run discuss→plan→execute on Phase 1 anyway — rejected as
   actively dangerous: Phase 1's own success criteria include "a fresh `git init`," and an
   executor agent given that criterion as an outstanding must-have could attempt to
   re-initialize git history, destroying the 15 real commits (`4866621`..`4719fa2`) already
   on `master`. Phase 1 is explicitly documented as "a hard, irreversible gate" — not safe
   to let an automated pipeline re-touch.
3. Stop and ask the user — precluded by the explicit "do not stop to ask me anything"
   instruction; this blocker had a defensible autonomous resolution (direct evidence-based
   verification) so it did not need to escalate further.

**Why:** The codebase evidence is real and checkable (not just asserted prose), so marking
the phase verified-by-evidence is honest; skipping it from automated re-execution is the
only choice that doesn't risk destroying already-shipped, irreversible work.

---

## [DECISION] Execute plans one at a time; use the harness's native worktree isolation, not GSD's manual bash choreography

**Phase:** 2 (and, by default, 3-5)

**What was ambiguous:** GSD's `execute-phase` workflow normally dispatches each plan's
executor into an isolated git worktree via a fairly involved bash choreography (manifest
tracking, per-agent worktree create/merge/cleanup, cwd-drift guards). Phase 2's three plans
are strictly sequential — each wave has exactly one plan, all three touch overlapping files
by design — so I first tried running executors directly on the main tree with no isolation
at all. The harness itself refused: `Agent()` for `subagent_type="gsd-executor"` on this
project resolves dispatch isolation to `harness-worktree` and hard-requires
`isolation="worktree"` on the call.

**Option chosen:** Keep plans strictly sequential (one executor at a time, next one only
starts after the previous is merged back), but use the Agent tool's own built-in
`isolation="worktree"` parameter for each dispatch, rather than replicating GSD's manual
manifest/merge/cleanup bash script by hand. After each executor returns, merge its branch
back with `git merge --no-ff` and remove the worktree myself.

**Alternatives considered:**
1. Hand-replicate the full GSD worktree manifest/cleanup bash — rejected: higher risk of
   getting the bash wrong and leaving stray worktrees/branches, when the harness already
   provides the same isolation guarantee natively through the Agent tool's own mechanism.
2. Run without isolation — rejected: the harness enforces it; not optional here.

**Why:** The isolation *guarantee* (an executor can't step on the orchestrator's working
tree) is what matters; GSD's own bash script and the harness's native worktree mode both
deliver it. Using the native mechanism is simpler and lower-risk than reimplementing GSD's
version, and satisfies the harness's hard requirement.

---

## [DECISION] Treat 0-Critical/0-Warning + Info-only as auto-fix loop convergence

**Phase:** 2 (code-review --fix --auto loop)

**What was ambiguous:** The code-review-fix auto-iteration loop's documented stop condition
is `02-REVIEW.md`'s frontmatter `status: clean`. After 3 review/fix iterations, iteration 3
found 0 Critical and 0 Warning findings — but 3 Info-level findings remained (test-coverage
gaps around the iteration-1 fixes, plus one pre-existing minor status-literal reuse), so the
frontmatter `status:` field read `issues_found`, not literally `clean` (the field means "any
findings exist at all," not "any blocking findings exist").

**Option chosen:** Treat this as effective convergence — stop the loop, do not spawn a
4th iteration. `fix_scope` for every pass was `critical_warning` (the default, no `--all`
flag), so Info findings were never in scope for the fixer in the first place; there was
nothing left to fix within the run's own declared scope.

**Alternatives considered:**
1. Re-invoke with `--all` to also fix the 3 Info items — rejected: `--all` was never
   requested for this run, and the Info items are genuinely optional (missing regression
   tests for already-fixed code, and a cosmetic status-literal reuse) rather than defects.
2. Treat "not literally `clean`" as non-convergence and loop again anyway — rejected: the
   loop is capped at 3 iterations specifically because further looping past the meaningful
   stop condition (no in-scope findings) burns time for no benefit.

**Why:** The auto-fix loop's purpose is to close Critical/Warning findings before the phase
is considered done; that bar was cleared. Documented the 3 remaining Info items in
`02-REVIEW-FIX.md` rather than silently dropping them.

---
