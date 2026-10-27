---
id: builtin/release-version
name: release-version
description: Use when asked to prepare and publish a software release; 更新项目版本号、更新 CHANGELOG、执行发布流程、发布新版本、发版。
version: 1.0.0
type: prompt
metadata:
  keywords: "release, publish, changelog, 发布, 发版, 版本发布"
  triggers: "更新版本并发布, 发布新版本, 执行发布流程, publish a release"
---

# Release a requested version

Inspect the target repository's release instructions, current version, changelog,
Git state, tags, open work, and CI before choosing the release scope. Preserve
unrelated work. Use the user's requested version when appropriate; resolve any
conflicting existing tag or release before publishing.

Update the version-bearing files and release notes required by that repository.
Run its relevant tests, review, build and release checks, and retain evidence of
their results. A failed, missing or incomplete required check blocks publication.

Publish only when the user has authorized that action and all required gates
pass. Follow the repository's normal release procedure rather than assuming a
particular language, package manager or hosting service. Verify the published
tag, target commit, assets and resulting CI; report remaining limitations.
