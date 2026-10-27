---
id: builtin/worktree-convergence
name: worktree-convergence
description: Safely converge existing Git worktrees and branches after examining each one; 逐一评审并收敛已有 worktree 和分支，保留未合并工作。
version: 1.0.0
type: prompt
metadata:
  keywords: "worktree, worktrees, 收敛, 分支收敛, worktree 收敛, 未合并工作, convergence"
  triggers: "逐一评审收敛所有 worktree 和分支, 收敛所有 worktree 和分支, converge worktrees and branches"
---

# Review and converge worktrees

Start with a read-only inventory of local and remote branches, checkouts,
detached heads, stashes, submodules, ownership, and active work. Record each
base and actual committed, staged, unstaged, untracked and ignored content;
do not print credentials or private content. Compare commits and trees with the
actual target using ancestry and patch evidence; squash merges and reverts need
separate examination. A similar branch name or commit subject is not proof.

For unfinished work within the user's scope, review and verify the affected
changes, resolve real defects, and follow the repository's merge and CI gates.
Do not combine unrelated changes just to make a checkout clean. Check ownership
and activity through task attachments, locks, sessions and available owner
records; absence of evidence is not proof of inactivity. Ambiguous ownership
and work owned by another active task are report-only unless authorized.
Before removing anything, record and preserve unique commits and all staged,
unstaged, untracked and ignored data that must survive. Verify the preservation
outside the checkout and verify recoverability before removal, including a
round-trip comparison of saved content and Git state where applicable; keeping
a branch does not preserve uncommitted files. Retain the current session's own
checkout. Stop cleanup if preservation or recovery verification fails.
Never use force removal, hard reset, destructive clean, or forced branch deletion
as a substitute for this verification. If preservation cannot be verified,
retain the checkout. Use the application's managed-worktree archive mechanism
when applicable, and verify its result before claiming cleanup.

For each disposition record the source and target revisions, review findings,
test commands and exit status, applicable CI run and conclusion, preservation
artifact location and verification, authorization, and operations performed.
Report retained work and blockers. Remote branch removal requires authorization
and proof that its work is retained or recoverable. A successful source review
alone does not prove that the merged tree or its CI passed.
