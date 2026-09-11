合成 fixture：pi 风格 NITS 段，bullet 跨行缠绕。不代表任何真实 gate。

```
VERDICT: PASS_WITH_NITS

MAJOR:
- replay harness resolves relative output paths against the invocation
  directory instead of the repo root, so running from elsewhere writes
  the report to the wrong place.

NITS:
- purge reminder for the retention eval set lives only in a yaml comment
  and nothing will fire on the purge date.
- calibration tolerance comment is stale after the label audit.

NOTES:
- trailing note that is not a finding.
```
