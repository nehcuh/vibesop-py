---
id: builtin/adversarial-panel
name: adversarial-panel
description: >-
  Use when the user asks to pull latest commits and run a multi-lane
  independent adversarial panel (拉取最新, 多路独立对抗, 独立对抗复审).
  Not a full-repo diagnose-fix-merge.
tags: [adversarial panel, multi-lane panel, pull latest, frozen diff,
       拉取最新, 多路独立对抗, 独立对抗, 对抗复审, 对抗评审,
       five lenses, refute-first]
triggers:
  - "多路独立对抗"
  - "独立对抗复审"
  - "拉取最新"
  - "pull latest and adversarial review"
  - "multi-lane independent adversarial review"
  - "/adversarial-panel"
  - "/adversarial-review"
version: 1.0.0
allowed-tools:
  - Read
  - Grep
  - Bash
  - Agent
intent: >-
  Fast-forward pull origin/main, freeze the shipping-surface patch, then run five
  independent finder lenses with refute-first verification and a synthesizer.
namespace: builtin
type: prompt
---

# Pull Latest + Multi-Lane Independent Adversarial Review

> Trigger: "拉取最新代码并使用多路独立对抗进行复审"

Discipline: **this is a frozen-diff review, not diagnose-fix-merge.**
If routing selected `deep-diagnosis-optimization` but the user named
多路独立对抗 / adversarial review, override and follow this skill.

## When NOT to use

- Full-repo audit, batch fixes, CI-green, merge → `deep-diagnosis-optimization`
- Walk the agent's own uncommitted diff before push → `code-review`
- Synthesizer already returned REQUEST CHANGES → `adversarial-arbitration`

## Steps

### 1. Pull without losing local session notes

- If `memory/session.md` would conflict with the incoming tree, stash it
  with a named message. Do not pop unrelated stashes.
- `git fetch origin` then **ff-only** onto `origin/main`.
  Refuse merge commits and force-with-lease onto main.

### 2. Freeze the review surface

- Record `base` (pre-pull HEAD) and `head` (post-pull HEAD).
- Diff the shipping surface only: `src/`, `scripts/`, `tests/`, `ci/`,
  `.github/`, `pyproject.toml`, `CHANGELOG.md`. Skip research/essays
  unless the user named them.
- Write a frozen patch file. Finders read that file, not a moving tree.

### 3. Retarget the workflow to this pull

- Registered Grok workflow: `adversarial-review`.
- If lens briefs still name an older CHANGELOG version, pass `args.theme`,
  `args.must_read`, and current `[Unreleased]` / latest version sections.
  Do not review 8.3.0 when HEAD is 8.5.0.

### 4. Run five independent lenses, then verify

Lenses (one agent each, no shared findings): **correctness, security,
concurrency, tests, claims-consistency**.

Then one skeptic per finding. Default **refute**. `real=true` only with
evidence inspected in the current tree.

On Grok: launch the registered workflow with `args.base`, `args.head`,
`args.patch`. Elsewhere: spawn the same 5+N panel yourself.

During review, do not edit `src/`.

### 5. Stop at the synthesizer

Report confirmed / rejected / unverified. Do not start `fix-from-review`
and do not treat REQUEST CHANGES as a merge gate — hand off to
`adversarial-arbitration` when the user (or the synthesizer) asks whether
findings are real defects.

## Anti-Patterns

- Taking `deep-diagnosis-optimization` because it scored 88%
- Popping an unrelated stash after the pull
- Letting finders see each other's notes
- Pasting the whole patch into a finder prompt
- Editing the tree while the frozen patch is still the review surface

## Exit Criteria

- [ ] ff-only pull recorded (base, head, frozen patch path)
- [ ] Five lenses ran; each verifier defaulted to refute
- [ ] Synthesizer counts (confirmed / rejected / unverified) reported
- [ ] No diagnose-fix-merge; no unrelated stash pop
---
