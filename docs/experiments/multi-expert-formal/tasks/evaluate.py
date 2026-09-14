"""Hidden host evaluator and reference/mutant sensitivity self-check."""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from .catalog import TASKS
from .cases import hidden_cases
from .common import check, copy_workspace, disk_value, invoke, same, step
from .oracles import MUTANTS, REFERENCES


def _run_step(case_dir: Path, item: dict, task: dict, home: Path | None) -> dict:
    env = dict(item.get("env") or {})
    volumes = []
    extra_tmpfs = tuple(task.get("extra_tmpfs") or ())
    if task.get("home_task"):
        env.setdefault("VIBE_HOME", "/tmp/vibe-home")
        if home is not None:
            volumes.append((str(home), "/tmp/vibe-home", "rw"))
            extra_tmpfs = ()
    return invoke(
        case_dir,
        item["request"],
        entry=item.get("entry") or "app.py",
        writable=bool(task.get("writable")),
        env=env or None,
        extra_tmpfs=extra_tmpfs,
        volumes=tuple(volumes),
    )


def evaluate(task_id: str, workspace: Path, *, visible_only: bool = False) -> dict:
    if task_id not in TASKS:
        return {"passed": False, "checks": [check("task_id", False, "unknown task")]}
    workspace = Path(workspace).absolute()
    if not workspace.is_dir() or workspace.is_symlink():
        return {"passed": False, "checks": [check("workspace", False, "invalid workspace")]}
    task = TASKS[task_id]
    for required in task["required_files"]:
        if not (workspace / required).is_file():
            return {"passed": False, "checks": [check("required:" + required, False, "missing")]}
    from .cases import visible_cases

    scenarios = hidden_cases(task_id) if not visible_only else visible_cases(task_id)
    if task_id == "config-render-resolve-v1" and not visible_only:
        scenarios = list(scenarios) + [[
            step(
                "mapped_not_guessed",
                {"op": "resolve", "platform": "gamma", "id": "alpha"},
                {"path": "rendered/gamma/odd/entry.md", "content": "host-seeded\n"},
            )
        ]]
    if task_id == "config-adapter-vs-entry-v1" and not visible_only:
        scenarios = list(scenarios) + [[
            step(
                "mapped_not_guessed",
                {"op": "lookup", "id": "alpha"},
                {"path": "bound/odd/entry.txt", "content": "host-seeded\n", "via": "adapter"},
                entry="adapter.py",
            )
        ]]
    checks = []
    try:
        with tempfile.TemporaryDirectory(prefix="formal-eval-") as tmp:
            base = Path(tmp) / "base"
            base.mkdir()
            copy_workspace(workspace, base)
            for index, steps in enumerate(scenarios):
                case_dir = Path(tmp) / f"case-{index}"
                shutil.copytree(base, case_dir)
                if task.get("writable") and (case_dir / "manifest").exists():
                    shutil.rmtree(case_dir / "manifest", ignore_errors=True)
                if task.get("writable") and (case_dir / "hooks").exists():
                    shutil.rmtree(case_dir / "hooks", ignore_errors=True)
                if task.get("writable") and (case_dir / "rendered").exists():
                    shutil.rmtree(case_dir / "rendered", ignore_errors=True)
                if task.get("writable") and (case_dir / "data").exists():
                    shutil.rmtree(case_dir / "data", ignore_errors=True)
                if task.get("writable") and (case_dir / "bindings.json").exists():
                    (case_dir / "bindings.json").unlink()
                if task.get("writable") and (case_dir / "bound").exists():
                    shutil.rmtree(case_dir / "bound", ignore_errors=True)
                home = None
                if task.get("home_task"):
                    home = Path(tmp) / f"home-{index}"
                    home.mkdir()
                if steps and steps[0]["name"] == "mapped_not_guessed" and task_id == "config-render-resolve-v1":
                    dest = case_dir / "rendered/gamma/odd/entry.md"
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text("host-seeded\n", encoding="utf-8")
                    man = case_dir / "manifest/gamma.json"
                    man.parent.mkdir(parents=True, exist_ok=True)
                    man.write_text(json.dumps({"alpha": "rendered/gamma/odd/entry.md"}), encoding="utf-8")
                if steps and steps[0]["name"] == "mapped_not_guessed" and task_id == "config-adapter-vs-entry-v1":
                    dest = case_dir / "bound/odd/entry.txt"
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text("host-seeded\n", encoding="utf-8")
                    (case_dir / "bindings.json").write_text(json.dumps({"alpha": "bound/odd/entry.txt"}), encoding="utf-8")
                for item in steps:
                    run = _run_step(case_dir, item, task, home)
                    passed = run["ok"] and same(run.get("value"), item["expected"])
                    detail = "matched CLI contract" if passed else (
                        run["detail"] if not run["ok"] else "JSON mismatch: " + repr(run.get("value"))[:500]
                    )
                    for relative, expected in item["disk"].items():
                        try:
                            disk_ok = disk_value(case_dir, relative, expected)
                        except (OSError, ValueError, UnicodeError):
                            disk_ok = False
                        if not disk_ok:
                            passed = False
                            detail += "; disk mismatch: " + relative
                    if task.get("home_task") and passed:
                        leaked = (case_dir / "items").exists() or (case_dir / "config.json").exists()
                        if leaked:
                            passed = False
                            detail += "; wrote task data into cwd"
                    checks.append(check(item["name"], passed, detail))
    except (OSError, ValueError) as exc:
        checks.append(check("workspace", False, exc))
    return {"passed": bool(checks) and all(c["passed"] for c in checks), "checks": checks}


def evaluate_visible(task_id: str, workspace: Path) -> dict:
    return evaluate(task_id, workspace, visible_only=True)


def self_check() -> dict:
    """Reference must pass; stub and domain mutant must fail named contracts."""
    checks = []
    with tempfile.TemporaryDirectory(prefix="formal-selfcheck-") as tmp:
        workspace = Path(tmp) / "candidate"
        workspace.mkdir()
        for task_id, files in REFERENCES.items():
            for name, content in files.items():
                path = workspace / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            if "adapter.py" not in files and (workspace / "adapter.py").exists():
                (workspace / "adapter.py").unlink()
            # Keep any extra initial files from the catalog (e.g. sources/alpha.txt).
            for name, content in TASKS[task_id]["files"].items():
                if name in files or name == "visible.json":
                    continue
                path = workspace / name
                if not path.exists():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(content, encoding="utf-8")
            good = evaluate(task_id, workspace)
            failed = [c["name"] + ": " + c["detail"] for c in good["checks"] if not c["passed"]]
            checks.append(check(
                task_id + "/reference",
                good["passed"],
                f'{len(good["checks"])} checks; ' + ("all passed" if not failed else repr(failed[:8])),
            ))
            stub_files = dict(TASKS[task_id]["files"])
            for name, content in stub_files.items():
                path = workspace / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            bad = evaluate(task_id, workspace)
            checks.append(check(
                task_id + "/scaffold",
                good["passed"] and not bad["passed"],
                "scaffold failures=" + str(sum(1 for c in bad["checks"] if not c["passed"])),
            ))
            mutant = MUTANTS[task_id]
            target = mutant["target"]
            for name, content in files.items():
                (workspace / name).write_text(content, encoding="utf-8")
            for name, content in mutant.items():
                if name == "target":
                    continue
                (workspace / name).write_text(content, encoding="utf-8")
            for name, content in TASKS[task_id]["files"].items():
                if name in mutant or name in files or name == "visible.json":
                    continue
                path = workspace / name
                if not path.exists():
                    path.write_text(content, encoding="utf-8")
            mutant_result = evaluate(task_id, workspace)
            caught = [
                c["name"]
                for c in mutant_result["checks"]
                if not c["passed"] and str(c["detail"]).startswith("JSON mismatch:")
            ]
            passed = (
                good["passed"]
                and not mutant_result["passed"]
                and target in caught
                and mutant.get("app.py") != files.get("app.py")
            )
            if task_id == "config-adapter-vs-entry-v1":
                passed = good["passed"] and not mutant_result["passed"] and target in caught
            checks.append(check(task_id + "/domain_mutant", passed, "semantic failures: " + repr(caught)))
        (workspace / "app.py").write_text("while True: pass\n", encoding="utf-8")
        timeout = invoke(workspace, {}, timeout=2)
        checks.append(check("harness/timeout", not timeout["ok"] and "timed out" in timeout["detail"], timeout["detail"]))
        (workspace / "app.py").write_text("raise SystemExit(3)\n", encoding="utf-8")
        exited = invoke(workspace, {})
        checks.append(check("harness/nonzero_exit", not exited["ok"] and "container exit 3" in exited["detail"], exited["detail"]))
        (workspace / "app.py").write_text('print("not json")\n', encoding="utf-8")
        invalid = invoke(workspace, {})
        checks.append(check(
            "harness/invalid_json",
            not invalid["ok"] and "JSON" in invalid["detail"],
            invalid["detail"],
        ))
    return {"passed": all(c["passed"] for c in checks), "checks": checks}


if __name__ == "__main__":
    report = self_check()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["passed"] else 1)
