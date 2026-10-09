# 2026-10-09 冻结诊断证据保存与恢复

本目录保存历史诊断，不代表后续修复已经验收。REPORT.md、evidence/README.md、manifest.json 及所有保留证据均为原始字节。历史 README 中的命令和原路径保持原样，当前位置以 [locations.json](locations.json) 为准。原 manifest 的57项文件列表不含报告和 manifest 自身，其历史路径/哈希没有重写。

59 个原件、5344995 字节均保存在本地冷归档：`/Users/huchen/Projects/vibesop-py-archives/2026-10-09/deep-diagnosis-original.tar.gz`，SHA-256 `9a8deed3a9355c5788041b5ce4dc9cca054d286b4d010e57f86f4c849ce79ec9`。Git 保留57份原件副本：30份日志更名 `.log.txt`、10份探针更名 `.py.txt`，其字节/哈希不变。仅 coverage JSON 和完整 pytest XML（合计4885563字节）保存在冷归档，node24 XML仍在 Git。Git clone 不包含冷归档；这是同盘恢复材料。迁移不会执行探针或调用模型，恢复后也不自动执行。

## 恢复全部原件

从项目根目录运行下列命令，只向一个不存在的新目录写出原始59文件；不用 extractall，不覆盖目标。必须先确保冷归档存在。修改 restore_to 的具体新路径后再运行。

```sh
uv run --no-sync python -B - <<'PYRESTORE'
from pathlib import Path
import hashlib, json, tarfile
locations = json.loads(Path('docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/locations.json').read_text())
archive = Path(locations['archive_path'])
assert hashlib.sha256(archive.read_bytes()).hexdigest() == locations['archive_sha256']
restore_to = Path('/tmp/vibesop-diagnosis-restored-20261009')
assert not restore_to.exists() and not restore_to.is_symlink()
verified = []
with tarfile.open(archive, 'r:gz') as tar:
    for row in locations['files']:
        member = tar.getmember(row['archive_member'])
        assert member.isfile()
        data = tar.extractfile(member).read()
        assert len(data) == row['bytes']
        assert hashlib.sha256(data).hexdigest() == row['sha256']
        relative = Path(row['archive_member'])
        assert not relative.is_absolute() and '..' not in relative.parts
        verified.append((relative, data))
restore_to.mkdir()
for relative, data in verified:
    target = restore_to / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as stream:
        stream.write(data)
print('restored', len(verified), 'files to', restore_to)
PYRESTORE
```

## 完整映射

| 原仓库路径 | Git 保存路径 | 冷归档成员 | 字节数 | SHA-256 |
|---|---|---|---:|---|
| `docs/reviews/2026-10-09-deep-diagnosis/REPORT.md` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/REPORT.md` | `2026-10-09-deep-diagnosis/REPORT.md` | 26616 | `42e57e2f9bc7a7eeb3b98416f57e723a309e5682ad11b69ea806558c2054a3ee` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/README.md` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/README.md` | `2026-10-09-deep-diagnosis/evidence/README.md` | 3398 | `f29ec7e8a8ec842b9142d71b990e7d77cc5f91d2a1313f28f754a2132909b672` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/artifact-links.log` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/artifact-links.log.txt` | `2026-10-09-deep-diagnosis/evidence/artifact-links.log` | 151 | `f813bf7585a3789f7c927019eb1a88ce154da3c6518ce4fa1d53f9998abbd8d5` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/baseline.json` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/baseline.json` | `2026-10-09-deep-diagnosis/evidence/baseline.json` | 484 | `7bafa9e82d404fed5bda189dde43541075bd368c9f5127b75919e8349a8ad6c7` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/container-wheel-tool.log` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/container-wheel-tool.log.txt` | `2026-10-09-deep-diagnosis/evidence/container-wheel-tool.log` | 2072 | `9b7f264002dace5411bc66162d1aa166765980fe482ec4abfc72fdbe147555a1` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/cross-architecture.log` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/cross-architecture.log.txt` | `2026-10-09-deep-diagnosis/evidence/cross-architecture.log` | 2067 | `78c802000127aff0303e10cc6d46803d78bfd39d443df251df69a60260272069` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/cross-correctness.log` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/cross-correctness.log.txt` | `2026-10-09-deep-diagnosis/evidence/cross-correctness.log` | 470 | `b67239471aaeaf575a8781d6274acdcd10e92e2bd0709d3215a0d14b8ddb018e` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/decision-source.log` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/decision-source.log.txt` | `2026-10-09-deep-diagnosis/evidence/decision-source.log` | 171 | `f42fc56e7c8e801db4347b0ffbe6324d2eb895dd6fb8422d547e103344653583` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/deepseek-e2e.log` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/deepseek-e2e.log.txt` | `2026-10-09-deep-diagnosis/evidence/deepseek-e2e.log` | 1112 | `c8e1f4ccd571abc4d2a895bc2566a9916e0f271dfce1bf8e983c0aa343a0e3f3` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/deepseek-review.log` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/deepseek-review.log.txt` | `2026-10-09-deep-diagnosis/evidence/deepseek-review.log` | 9890 | `55e135edbcc446f99f7c540ac29b4e2df91efe545be052a1d598806f234f969d` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/docker-derived-build.log` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/docker-derived-build.log.txt` | `2026-10-09-deep-diagnosis/evidence/docker-derived-build.log` | 2495 | `0989f5e2ac400a0d7a855823a5133656f59a6bfcadcf45d15bdff7930a426bca` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/eval-routing.json` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/eval-routing.json` | `2026-10-09-deep-diagnosis/evidence/eval-routing.json` | 27740 | `7df25c7793e613adf35b5aa902fdc54be3c420747c5647a8fa7b9d156f2603b0` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/eval-routing.log` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/eval-routing.log.txt` | `2026-10-09-deep-diagnosis/evidence/eval-routing.log` | 1804 | `015e382d50d5ed576e41472413330493aafa44349c9b4c534ea498f8b9c58c65` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/final-container-coverage.json` | `coldarchive only` | `2026-10-09-deep-diagnosis/evidence/final-container-coverage.json` | 3815898 | `0339aa176fd59913fb4df2aeaf6e115c07c2694a4a5093b538d91958b5a5a6dc` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/final-container-pytest.log` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/final-container-pytest.log.txt` | `2026-10-09-deep-diagnosis/evidence/final-container-pytest.log` | 68447 | `f7d182f7225fcab11fc7448b9e86ba566f3d7fb66673a6e025c740159bbb2610` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/final-container-pytest.xml` | `coldarchive only` | `2026-10-09-deep-diagnosis/evidence/final-container-pytest.xml` | 1069665 | `c2f2eed7378f55b504a55c7668f4c5b3a2d80433abfbdb7898dc80e5ead0d209` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/grok-review.log` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/grok-review.log.txt` | `2026-10-09-deep-diagnosis/evidence/grok-review.log` | 481 | `cfdb71a0004d0e8304b3f8710a16f72fc0eaa2ec26ad0449d442f63d98366323` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/host-format.log` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/host-format.log.txt` | `2026-10-09-deep-diagnosis/evidence/host-format.log` | 28 | `86eb002746d4cf95ee252350d80cab2274e2a66690ae1a6ed8904ef89dae2a10` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/host-ruff.log` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/host-ruff.log.txt` | `2026-10-09-deep-diagnosis/evidence/host-ruff.log` | 19 | `82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/host-type.log` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/host-type.log.txt` | `2026-10-09-deep-diagnosis/evidence/host-type.log` | 30 | `56882e01cb80173ef053c4096e4ee43e3123a15f5c0a06715f96988d48fbd91c` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/independent-review-prompt.txt` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/independent-review-prompt.txt` | `2026-10-09-deep-diagnosis/evidence/independent-review-prompt.txt` | 67641 | `b83ac459825c562ab286138bcb5cc9e3d507cfc876f26046a3638c16174450c5` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/manifest.json` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/manifest.json` | `2026-10-09-deep-diagnosis/evidence/manifest.json` | 9477 | `e41adaf3b174e25003d3d6151d7ed0ed384bdd021cd9387faf02d48fa8714c9a` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/node24-pytest.log` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/node24-pytest.log.txt` | `2026-10-09-deep-diagnosis/evidence/node24-pytest.log` | 378 | `3017bc6c78f696c6a8cc1a763e2ec4487be539db963721f5e5d73ca4f31049a6` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/node24-pytest.xml` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/node24-pytest.xml` | `2026-10-09-deep-diagnosis/evidence/node24-pytest.xml` | 31259 | `bf0e3b133d498d5ea0b03bbf32f16f3cd913708a144c8320c2d9be983142f162` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/node24-setup.log` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/node24-setup.log.txt` | `2026-10-09-deep-diagnosis/evidence/node24-setup.log` | 644 | `48d4399bfcc77c4ba8ea8167761c30153549441eb2af7784aa81088a8fe9a6d2` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/pack-functional.log` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/pack-functional.log.txt` | `2026-10-09-deep-diagnosis/evidence/pack-functional.log` | 484 | `671a9901bf355054a08b22a11b4e5ce4fd3506f46e3965c1fdbab2967e92624b` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/platform-render.log` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/platform-render.log.txt` | `2026-10-09-deep-diagnosis/evidence/platform-render.log` | 212 | `771377fbb19044d13b1a7ab7004ffe92b29695a35e415e91b592f0b03e1e3957` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/platform.log` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/platform.log.txt` | `2026-10-09-deep-diagnosis/evidence/platform.log` | 514 | `242b244635b6e53eaee5be6a38752ad6b16bbc861090b359e07e52b39283a02d` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/probes/cross-architecture-probes.py` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/probes/cross-architecture-probes.py.txt` | `2026-10-09-deep-diagnosis/evidence/probes/cross-architecture-probes.py` | 3503 | `37da4170daa6ec22bb9e99e10d852694c6fc5b0e07c9a5ffe6622b83c14301b8` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/probes/cross-correctness.py` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/probes/cross-correctness.py.txt` | `2026-10-09-deep-diagnosis/evidence/probes/cross-correctness.py` | 4841 | `e0545bff144fee0526ff739d29fdfa6e269087860a750f15d1dafb4840179ca2` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/probes/deepseek-e2e.py` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/probes/deepseek-e2e.py.txt` | `2026-10-09-deep-diagnosis/evidence/probes/deepseek-e2e.py` | 406 | `025774064cfc2a7c01b0788d020883c77fc67a963123ce9443ce3376d7afd33b` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/probes/deepseek-review.py` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/probes/deepseek-review.py.txt` | `2026-10-09-deep-diagnosis/evidence/probes/deepseek-review.py` | 525 | `3e42c781ae4509ed68b8add27ec9ae25d9fa7d66a9a7e04f4e6f3b4cfa636e74` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/probes/functional-cross.py` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/probes/functional-cross.py.txt` | `2026-10-09-deep-diagnosis/evidence/probes/functional-cross.py` | 2474 | `892418516149c4b572caa2f403d4c5d13c15b1ce8b1c8a2bb4fd3a5a11386206` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/probes/pack-functional.py` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/probes/pack-functional.py.txt` | `2026-10-09-deep-diagnosis/evidence/probes/pack-functional.py` | 1673 | `a154da4d7327c6bb47c4e5cf265f4307a0de360563db91b69941f5032ff453c0` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/probes/platform-security-more.py` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/probes/platform-security-more.py.txt` | `2026-10-09-deep-diagnosis/evidence/probes/platform-security-more.py` | 1827 | `5bfbc9f045335579b0b57a9d8b930509aa9e60d1b78070f33197422a48e86e75` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/probes/platform-security-probes.py` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/probes/platform-security-probes.py.txt` | `2026-10-09-deep-diagnosis/evidence/probes/platform-security-probes.py` | 2168 | `4516c0f021b874735682f115b4b424c85a2d8af873c58f31783a2de24d297ef0` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/probes/routing-runtime.py` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/probes/routing-runtime.py.txt` | `2026-10-09-deep-diagnosis/evidence/probes/routing-runtime.py` | 5110 | `983e3da13d29fa330a1f1e6f17c69539644d015db513cfed2af9b954bf4fef32` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/probes/value-probes.py` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/probes/value-probes.py.txt` | `2026-10-09-deep-diagnosis/evidence/probes/value-probes.py` | 3368 | `49455c022f7b434fb9d379e152ee5ffda52e64e085016afc511d8e9633d09636` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/remote-main-sha.txt` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/remote-main-sha.txt` | `2026-10-09-deep-diagnosis/evidence/remote-main-sha.txt` | 41 | `0047060197411826487eee3a4d7ad0910899057bb7c508a58bf77e322175fb4a` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/remote-runs.json` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/remote-runs.json` | `2026-10-09-deep-diagnosis/evidence/remote-runs.json` | 924 | `8401950d3a42f3e9ec1e63358c76c61576e37217c3a3266f3db207435d7d817f` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/reviews/cross-architecture-tests.txt` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/reviews/cross-architecture-tests.txt` | `2026-10-09-deep-diagnosis/evidence/reviews/cross-architecture-tests.txt` | 8959 | `0aad4f602168f37ccadacec5709abf5eb6f8c76a6636c976fd6f169d39ed819c` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/reviews/cross-correctness-integration.txt` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/reviews/cross-correctness-integration.txt` | `2026-10-09-deep-diagnosis/evidence/reviews/cross-correctness-integration.txt` | 10034 | `17e9bc614b14595f797469e1957113d484010d1cf8d7e5042ae328833add0947` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/reviews/cross-security-ops.txt` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/reviews/cross-security-ops.txt` | `2026-10-09-deep-diagnosis/evidence/reviews/cross-security-ops.txt` | 7959 | `4431e568f56adb486169cdf2b867cdc5b7e33ffb69da827bdd1cdbd015019a38` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/reviews/platform-security.txt` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/reviews/platform-security.txt` | `2026-10-09-deep-diagnosis/evidence/reviews/platform-security.txt` | 11576 | `c1c6832ee339e87da85b5f65f1bd734153a1fafbaa1b2968790235f6b2474a24` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/reviews/routing-runtime.txt` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/reviews/routing-runtime.txt` | `2026-10-09-deep-diagnosis/evidence/reviews/routing-runtime.txt` | 13060 | `ab230862b62523712166854dc7cff951a3e4927922d20f0bfaa010465a0735ac` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/reviews/synthesis.txt` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/reviews/synthesis.txt` | `2026-10-09-deep-diagnosis/evidence/reviews/synthesis.txt` | 3860 | `8856691ce4004783ca6db60f2c3f8db0dbc82b74aa082023f6ae381015310c72` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/reviews/value-research.txt` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/reviews/value-research.txt` | `2026-10-09-deep-diagnosis/evidence/reviews/value-research.txt` | 14196 | `bb88bedf94cf1bf2e7b2d6a60151215f4b83e0d0afe4819f33b486ec18d89eaf` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/routing-runtime.log` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/routing-runtime.log.txt` | `2026-10-09-deep-diagnosis/evidence/routing-runtime.log` | 2551 | `f2b45e6a6dcd67226215700ebeecffc590f150fc55f64514a8ddf0440f138561` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/snapshot-artifact-gate.log` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/snapshot-artifact-gate.log.txt` | `2026-10-09-deep-diagnosis/evidence/snapshot-artifact-gate.log` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/tracked-files.txt` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/tracked-files.txt` | `2026-10-09-deep-diagnosis/evidence/tracked-files.txt` | 80919 | `3cdf3356e077530556f22d13ccf2d5f71764fd5e55a598acc07eb5455bdc74fe` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/value-probes.log` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/value-probes.log.txt` | `2026-10-09-deep-diagnosis/evidence/value-probes.log` | 591 | `450e976c225a50aa24d70bceb00a3978fa8ae577ca21354acfdd33a958434443` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/wheel-claude-hook.log` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/wheel-claude-hook.log.txt` | `2026-10-09-deep-diagnosis/evidence/wheel-claude-hook.log` | 3 | `ca3d163bab055381827226140568f3bef7eaac187cebd76878e0b63e9e442356` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/wheel-grok-hook.log` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/wheel-grok-hook.log.txt` | `2026-10-09-deep-diagnosis/evidence/wheel-grok-hook.log` | 3139 | `c3ec5cc4adb4db132a0e80992ce9dbbbe9e6fc4058e7b5a4c7e048759a260b1d` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/wheel-quickstart-claude.log` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/wheel-quickstart-claude.log.txt` | `2026-10-09-deep-diagnosis/evidence/wheel-quickstart-claude.log` | 2827 | `471afd5f073baf556999c7cacf2bf5d033df732adfe61eb592946239094ea7f9` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/wheel-quickstart-grok.log` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/wheel-quickstart-grok.log.txt` | `2026-10-09-deep-diagnosis/evidence/wheel-quickstart-grok.log` | 2824 | `c0ddf11d54f6c1f803ab5c4e0a327439440ecb918c0925122bd571267061b85d` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/wheel-tool-claude-hook.log` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/wheel-tool-claude-hook.log.txt` | `2026-10-09-deep-diagnosis/evidence/wheel-tool-claude-hook.log` | 3171 | `d50dda25c887217e54c1ee369bf3cab068fc42a149b1ed587e0727f76b430728` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/wheel-tool-grok-hook.log` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/wheel-tool-grok-hook.log.txt` | `2026-10-09-deep-diagnosis/evidence/wheel-tool-grok-hook.log` | 3168 | `b5d54ac992df7107688e18d81348055339e263f292506260b62756fa7fe3779c` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/wheel-tool-quickstart-claude.log` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/wheel-tool-quickstart-claude.log.txt` | `2026-10-09-deep-diagnosis/evidence/wheel-tool-quickstart-claude.log` | 2827 | `471afd5f073baf556999c7cacf2bf5d033df732adfe61eb592946239094ea7f9` |
| `docs/reviews/2026-10-09-deep-diagnosis/evidence/wheel-tool-quickstart-grok.log` | `docs/archive/reviews/diagnosis/2026-10-09-deep-diagnosis/evidence/wheel-tool-quickstart-grok.log.txt` | `2026-10-09-deep-diagnosis/evidence/wheel-tool-quickstart-grok.log` | 2824 | `c0ddf11d54f6c1f803ab5c4e0a327439440ecb918c0925122bd571267061b85d` |
