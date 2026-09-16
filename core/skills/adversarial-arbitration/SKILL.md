---
id: builtin/adversarial-arbitration
name: adversarial-arbitration
description: >-
  Use when an adversarial-panel synthesizer votes to block merge, or the
  user asks whether confirmed findings are real defects versus opinions
  (真问题还是看法, D/T/J, 会诊, 合成器).
tags: [D/T/J, 真问题, 看法, 会诊, 合成器, 对抗合成, decidable, taste, COMMENT, 仲裁]
triggers:
  - "REQUEST CHANGES"
  - "对抗合成器"
  - "真的问题还是看法"
  - "真问题还是看法"
  - "D/T/J"
  - "classify review findings"
  - "/adversarial-arbitration"
  - "/review-arbitration"
version: 1.0.0
allowed-tools:
  - Read
  - Grep
intent: >-
  Classify confirmed adversarial findings as D, T, or J and let a human
  arbitrator sign COMMENT versus block-merge. The synthesizer is consult,
  not a merge gate.
namespace: builtin
type: prompt
---

# Arbitrate Adversarial REQUEST CHANGES (D / T / J)

> Trigger: synthesizer says REQUEST CHANGES / "这些是真的问题还是看法"

**发现不收敛，决策才收敛。** LLM 评审是会诊，不是手术同意书。

The workflow rule "any HIGH → REQUEST CHANGES" is a panel vote. It is not
authorization to block merge or to start `fix-from-review`.

## When NOT to use

- No synthesizer output yet → `adversarial-panel` first
- User already named which D-class bugs to fix → implement those only
- Ordinary pre-push walkthrough of your own diff → `code-review`

## Classification

| Class | Meaning | Has an end? |
|-------|---------|-------------|
| **D** | Contract / test / lint / public claim that can be decided | Yes |
| **T** | Observable behavior; depends on how much you measure | Coverage decides |
| **J** | Taste, more tests, unpromised next layer, "could be nicer" | **No** |

J spoken in D tone is the default LLM-review failure. An unlabeled HIGH
count is not a gate.

## Steps

### 1. Inventory confirmed findings only

Ignore rejected and unverified items. For each confirmed finding, write
class (D/T/J), one-line evidence, and whether it falsifies a **shipping**
claim (CHANGELOG / public contract / fail-closed gate).

### 2. What counts as a real problem

- Independently reproduced **D**
- **T** that falsifies a shipping claim (the product said X; the tree does not X)

Everything else is a viewpoint. Record it. Do not promote it to a merge
blocker.

### 3. Human sign-off

Ask the user to sign **COMMENT** or **REQUEST CHANGES**. Do not infer
sign-off from the synthesizer. Do not auto-start `fix-from-review`.

If they sign COMMENT: ship; punch-list the surviving D. If they sign
REQUEST CHANGES: fix only the D (and T that falsifies a claim) they named.

## Anti-Patterns

- Treating synthesizer HIGH as merge-blocking
- Implementing J-class "more tests" / "existence side-channel" / "unpromised
  next layer" because the finder sounded sure
- Starting `fix-from-review` without a human named scope
- Re-running finders to "get consensus" — findings do not converge

## Exit Criteria

- [ ] Every confirmed finding labeled D, T, or J with evidence
- [ ] Real problems = reproduced D + T that falsifies a shipping claim
- [ ] Human COMMENT vs REQUEST CHANGES recorded
- [ ] `fix-from-review` not started unless the user named the D-class fixes
---
