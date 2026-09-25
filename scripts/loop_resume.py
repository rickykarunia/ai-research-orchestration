"""Inspect and claim a wiki-to-output loop checkpoint."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import uuid
from pathlib import Path


PHASES = ("PLAN", "ACT", "REVIEW", "VERIFY", "FINISH")
_DECISION = re.compile(r"^\s*-\s*Putusan:\s*(LULUS|ULANG ACT|GAGAL)\s*$", re.MULTILINE)
_CLAIM = re.compile(r"\[K\d+\]|\[NEEDS SOURCE\]")


class LoopResumeError(RuntimeError):
    """Raised when checkpoint evidence cannot support a safe decision."""


class ActiveRunError(LoopResumeError):
    """Raised when another executor owns the loop lock."""


def _frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    values: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip('"\'')
    return values


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _decision(path: Path) -> str | None:
    match = _DECISION.search(_read_text(path))
    return match.group(1) if match else None


def _state_path(vault: Path, slug: str) -> Path:
    return vault / ".loop" / slug / "state.json"


def _output_path(vault: Path, state: dict) -> Path:
    relative = str(state.get("outputPath", "")).replace("/", "\\")
    if not relative or Path(relative).is_absolute():
        raise LoopResumeError("invalid state outputPath")
    return vault.joinpath(*relative.split("\\"))


def _result(phase: str | None, last: str | None, iteration: int, reason: str, *, blocked: bool = False) -> dict:
    return {
        "resume_phase": phase,
        "last_valid_phase": last,
        "iteration": iteration,
        "reason": reason,
        "blocked": blocked,
    }


def _active_lock(loop_dir: Path) -> dict | None:
    lock = loop_dir / "run.lock"
    if not lock.exists():
        return None
    try:
        value = json.loads(lock.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LoopResumeError(f"run.lock could not be read: {exc}") from exc
    if not isinstance(value, dict) or not value.get("runId"):
        raise LoopResumeError("run.lock has no runId")
    return value


def inspect_loop(vault: Path, slug: str) -> dict:
    """Return a deterministic resume decision without mutating the vault."""
    vault = Path(vault).resolve()
    state_path = _state_path(vault, slug)
    loop_dir = state_path.parent
    active_lock = _active_lock(loop_dir)
    if not state_path.exists():
        result = _result("PLAN", None, 0, "state.json not found; starting from PLAN", blocked=True)
        if active_lock:
            result["active_lock"] = active_lock
        return result

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LoopResumeError(f"state.json is invalid: {exc}") from exc
    if not isinstance(state, dict):
        raise LoopResumeError("state.json must be an object")
    if state.get("slug") != slug:
        raise LoopResumeError(f"state slug mismatch: {state.get('slug')!r} != {slug!r}")
    try:
        output = _output_path(vault, state)
    except LoopResumeError:
        raise
    expected_output = Path("3. output") / output.name
    declared_output = Path(str(state.get("outputPath", "")).replace("\\", "/"))
    if declared_output != expected_output:
        raise LoopResumeError(f"outputPath does not match the target: {declared_output}")

    try:
        iteration = int(state.get("iteration", 0))
    except (TypeError, ValueError) as exc:
        raise LoopResumeError("iteration must be an integer") from exc
    if iteration < 0:
        raise LoopResumeError("iteration must not be negative")

    plan = loop_dir / "plan.md"
    critique = loop_dir / "critique.md"
    verify = loop_dir / "verify.md"
    plan_valid = "## Peta klaim" in _read_text(plan)
    output_text = _read_text(output)
    output_meta = _frontmatter(output_text)
    output_valid = output_meta.get("loop-slug") == slug and bool(_CLAIM.search(output_text))
    critique_decision = _decision(critique)
    verify_decision = _decision(verify)

    if active_lock:
        result = _result(None, None, iteration, "run.lock is held by another executor", blocked=True)
        result["active_lock"] = active_lock
        return result

    phase = state.get("phase")
    phase_status = state.get("phaseStatus")
    if phase not in (None, *PHASES):
        raise LoopResumeError(f"unknown phase: {phase!r}")

    if phase == "FINISH" and phase_status == "complete" and output_meta.get("status") == "final":
        return _result(None, "FINISH", iteration, "FINISH already complete; no rewrite needed")

    if phase_status == "in_progress":
        if phase is None:
            raise LoopResumeError("phaseStatus in_progress without a phase")
        return _result(phase, None, iteration, f"phase {phase} not yet checkpointed as complete")

    if phase_status == "complete" and state.get("resumeFrom") in PHASES:
        next_phase = state["resumeFrom"]
        if next_phase == "ACT" and not plan_valid:
            raise LoopResumeError("checkpoint asks for ACT but plan.md is invalid")
        if next_phase in ("REVIEW", "VERIFY", "FINISH") and not output_valid:
            raise LoopResumeError(f"checkpoint asks for {next_phase} but output is invalid")
        return _result(next_phase, phase, iteration, f"resumeFrom checkpoint: {next_phase}")

    if not plan_valid:
        return _result("PLAN", None, iteration, "plan.md missing or lacks a Peta klaim section", blocked=True)
    if not output_valid:
        return _result("ACT", "PLAN", iteration, "PLAN valid, output not yet valid")
    if critique_decision == "ULANG ACT":
        return _result("ACT", "REVIEW", iteration + 1, "REVIEW asked for ULANG ACT")
    if critique_decision is None:
        return _result("REVIEW", "ACT", iteration, "ACT valid, critique has no decision yet")
    if critique_decision != "LULUS":
        raise LoopResumeError(f"unsupported critique decision: {critique_decision}")
    if verify_decision == "GAGAL":
        return _result("ACT", "VERIFY", iteration + 1, "VERIFY failed; back to ACT")
    if verify_decision is None:
        return _result("VERIFY", "REVIEW", iteration, "REVIEW passed, verify has no decision yet")
    if verify_decision != "LULUS":
        raise LoopResumeError(f"unsupported verify decision: {verify_decision}")
    if output_meta.get("status") == "final":
        return _result(None, "VERIFY", iteration, "output final after VERIFY; FINISH need not rerun")
    return _result("FINISH", "VERIFY", iteration, "VERIFY passed")


def acquire_lock(loop_dir: Path, run_id: str, executor: str) -> Path:
    """Create an exclusive lock or raise an actionable active-run error."""
    loop_dir = Path(loop_dir)
    loop_dir.mkdir(parents=True, exist_ok=True)
    lock_path = loop_dir / "run.lock"
    payload = {"runId": run_id, "executor": executor}
    try:
        with lock_path.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=True)
            handle.write("\n")
    except FileExistsError as exc:
        owner = _active_lock(loop_dir)
        raise ActiveRunError(f"run already active: {owner}") from exc
    return lock_path


def release_lock(lock_path: Path, run_id: str) -> None:
    """Remove only the lock path owned by run_id."""
    lock_path = Path(lock_path)
    try:
        owner = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LoopResumeError(f"run.lock could not be read: {exc}") from exc
    if owner.get("runId") != run_id:
        raise ActiveRunError("run.lock is not owned by this run_id")
    lock_path.unlink()


def self_test() -> None:
    with tempfile.TemporaryDirectory() as td:
        vault = Path(td)
        loop_dir = vault / ".loop" / "memo"
        loop_dir.mkdir(parents=True)
        (vault / "3. output").mkdir()
        (loop_dir / "state.json").write_text(json.dumps({
            "vault": vault.name,
            "slug": "memo",
            "outputPath": "3. output/memo.md",
            "phase": "PLAN",
            "iteration": 0,
        }), encoding="utf-8")
        (loop_dir / "plan.md").write_text("## Peta klaim\n", encoding="utf-8")
        assert inspect_loop(vault, "memo")["resume_phase"] == "ACT"
        lock = acquire_lock(loop_dir, "one", "codex")
        try:
            try:
                acquire_lock(loop_dir, "two", "claude")
            except ActiveRunError:
                pass
            else:
                raise AssertionError("active lock did not block the claim")
        finally:
            release_lock(lock, "one")
    print("PASS loop_resume self-test")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", type=Path)
    parser.add_argument("--slug")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--claim", action="store_true")
    parser.add_argument("--release", action="store_true")
    parser.add_argument("--run-id")
    parser.add_argument("--executor", default="codex")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        self_test()
        return 0
    if not args.vault or not args.slug:
        parser.error("--vault and --slug are required unless --self-test")
    loop_dir = args.vault / ".loop" / args.slug
    run_id = args.run_id or str(uuid.uuid4())
    try:
        if args.claim:
            path = acquire_lock(loop_dir, run_id, args.executor)
            print(json.dumps({"lock": str(path), "runId": run_id}, ensure_ascii=True))
            return 0
        if args.release:
            release_lock(loop_dir / "run.lock", run_id)
            print(json.dumps({"released": True, "runId": run_id}, ensure_ascii=True))
            return 0
        result = inspect_loop(args.vault, args.slug)
        print(json.dumps(result, ensure_ascii=True) if args.as_json else result)
        return 0 if not result["blocked"] else 2
    except LoopResumeError as exc:
        if args.as_json:
            print(json.dumps({"blocked": True, "reason": str(exc)}, ensure_ascii=True))
        else:
            print(f"BLOCKED: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
