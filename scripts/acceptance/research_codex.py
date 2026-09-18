"""Opt-in B05: three real Codex sessions in one isolated research workspace.

Generated model messages and tool events stay in the caller's untracked output directory.
This is never included in deterministic CI. It does not run Docker or training.
"""

import argparse
import json
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path


def run_session(
    command: list[str], prompt: str, root: Path, seconds: float
) -> tuple[int, str, str]:
    process = subprocess.Popen(
        command,
        cwd=root,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(prompt, timeout=seconds)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
        return 124, stdout, stderr
    return process.returncode, stdout, stderr


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-real-codex", action="store_true", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--correction-file",
        type=Path,
        required=True,
        help="Actual user's constraint correction, not a simulated user",
    )
    parser.add_argument("--seconds", type=int, default=600)
    parser.add_argument("--model", required=True, help="Explicitly authorized model")
    args = parser.parse_args()
    if not 1 <= args.seconds <= 600:
        parser.error("seconds must be between 1 and 600")
    cli, codex = shutil.which("agent-infra"), shutil.which("codex")
    if cli is None or codex is None:
        parser.error("agent-infra and codex must already be installed and on PATH")
    correction = args.correction_file.read_text(encoding="utf-8")
    root = args.output_dir.absolute()
    root.mkdir(parents=True, exist_ok=False)
    state, workspace = root / "state", root / "project"

    def platform(*arguments: str) -> dict[str, object]:
        result = subprocess.run(
            [cli, *arguments, "--state-dir", str(state)],
            capture_output=True,
            text=True,
            check=True,
            timeout=20,
        )
        return dict(json.loads(result.stdout))

    initialized = platform("init", str(workspace), "--goal", "比较位置编码对长上下文的影响")
    project = initialized["project"]
    if not isinstance(project, dict):
        raise RuntimeError("unexpected init output")
    identifier = str(project["project_id"])
    installed = platform("project", "research", "skill", identifier, "--install")
    common = (
        f"You are validating research planning with real tools. Work only in {workspace}; "
        f"control state is {state}. Read the skill at {installed['skill_path']}/SKILL.md "
        "and its command reference. "
        f"Use the installed executable {cli} (not uv); "
        f"every project command must use --state-dir {state}. "
        f"Project ID: {identifier}. Do not reinitialize. "
        "Do not use subagents, MCP tools, network searches, "
        "Docker, GPUs, training, package installs or change global configuration. "
        "Use only local test material, your research reasoning and the project CLI. "
        "Never edit the database or generated Markdown directly; use the public CLI. "
        "Keep the work small enough to complete within a few minutes. Reply in Chinese. "
    )
    prompts = [
        common + "Read context. The research goal is 比较位置编码对长上下文的影响. "
        "Form a small initial Brief and Plan with at least one understandable experiment. "
        "Data and budget have not been supplied; record unknowns and clearly label "
        "proposed choices as assumptions or inference. "
        "Save the draft using the CLI. Do not confirm it as adopted by the user. "
        "Explain remaining questions.",
        common + f"Read the stored context, then apply this actual user correction: {correction}\n"
        "Revise and save a new coherent version, preserving the original goal "
        "and stable experiment IDs. Record what changed and why. "
        "This authorizes the stated constraints, not an invented dataset or scientific conclusion. "
        "Do not claim the user adopted additional methodological choices. "
        "Do not start experiments.",
        common
        + "This is a fresh session. Recover the research state using only the project and CLI. "
        "Read context and run the planning check. Explain the current chosen constraints, "
        "what was changed, "
        "the unknowns, and next action. Do not create another revision or confirm a proposal. "
        "Do not assume access to earlier conversation messages.",
    ]
    deadline = time.monotonic() + args.seconds
    stages = []
    for number, prompt in enumerate(prompts, 1):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        (root / f"prompt-{number}.txt").write_text(prompt, encoding="utf-8")
        command = [
            codex,
            "-a",
            "never",
            "exec",
            "--model",
            args.model,
            "--skip-git-repo-check",
            "--ephemeral",
            "--json",
            "--sandbox",
            "read-only" if number == 3 else "workspace-write",
            "--cd",
            str(workspace),
            "--add-dir",
            str(state),
            "--output-last-message",
            str(root / f"answer-{number}.md"),
            "-",
        ]
        started = time.monotonic()
        code, stdout, stderr = run_session(command, prompt, root, remaining)
        (root / f"events-{number}.jsonl").write_text(stdout, encoding="utf-8")
        (root / f"stderr-{number}.log").write_text(stderr, encoding="utf-8")
        stage = {
            "stage": number,
            "model": args.model,
            "exit_code": code,
            "seconds": round(time.monotonic() - started, 2),
        }
        stages.append(stage)
        print(json.dumps(stage), flush=True)
        (root / "sessions.json").write_text(json.dumps(stages, indent=2), encoding="utf-8")
        if code != 0:
            break
        ctx = platform("project", "research", "context", identifier)
        (root / f"context-{number}.json").write_text(
            json.dumps(ctx, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(f"Evidence: {root}. Inspect actual tool events and saved revisions before accepting B05.")
    if len(stages) != 3 or any(s["exit_code"] != 0 for s in stages):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
