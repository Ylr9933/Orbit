# Research CLI (schema version 1)

Commands below are implemented. `PROJECT` is the UUID or original workspace directory.
Use an installed `agent-infra` or the repository venv executable. All commands accept `--state-dir`;
pass the same state root used by init. JSON goes to stdout, errors to stderr (exit 2).
Put `--state-dir` after the research subcommand, for example
`agent-infra project research context PROJECT --state-dir STATE_ROOT`; it is not a global option.
The save command validates JSON itself; no separate `jq` installation is required.

```sh
agent-infra project research context PROJECT
agent-infra project research show PROJECT --revision 1
agent-infra project research history PROJECT --limit 10
agent-infra project research diff PROJECT --from-revision 1 --to-revision 2
agent-infra project research check PROJECT
```

`context.document` is the latest complete editable draft. To revise it, preserve fields you are not
changing and write that object to a UTF-8 JSON file. Do not pass the entire context response to save.
Use `context.research_revision` as expected revision (0 for the first draft):

```sh
agent-infra project research save PROJECT --file draft.json --expected-revision 0 --reason "Initial research proposal"
```

The result contains `research.revision`, `research.digest`, and `projection.status`. A pending projection
means the draft was saved but one or more Markdown files were protected from overwrite. Saving a newer
draft leaves the previously accepted revision unchanged. JSON snapshots are limited to 256 KiB.

The following is a schema illustration, not a research proposal to copy unchanged:

```json
{
  "schema_version": 1,
  "brief": {
    "question": "",
    "background": "",
    "success_criteria": "",
    "constraints": [],
    "unknowns": []
  },
  "plan": {
    "summary": "",
    "experiments": [{
      "id": "pilot",
      "title": "",
      "hypothesis": "",
      "method": "",
      "controls": "",
      "variables": "",
      "inputs": [],
      "metrics": [],
      "outputs": [],
      "resource_request": null,
      "stopping_condition": ""
    }]
  },
  "claims": [],
  "next_step": ""
}
```

Only `schema_version` is required at the root; fields default to empty, experiments to an empty list.
Each included experiment needs a unique stable `id`. Unknown fields are rejected.

- An input is `{"path":"data/manifests/dataset.md","description":"...","version":"..."}`.
  Paths are relative to the project; nonexistent inputs may be saved and are reported by check.
  Version may be empty while undecided. Use a manifest to describe external data, not a symlink escape.
- A metric is `{"name":"validation loss","direction":"minimize"}`; direction is maximize/minimize/inspect.
  Metrics may be empty when human inspection is intended; check will mention this without rejecting save.
- Outputs are relative path strings. `resource_request` points to an existing Resources YAML, or is null
  while undecided. Check uses the Resources validator; no CPU/GPU is allocated.
- A claim is `{"text":"...","origin":"assumption","references":[]}`. Origins are user/sourced/inference/assumption.
  Sourced claims need references: public HTTP(S) URLs or project-relative files. URLs are not fetched by check.
- Background, summary, hypothesis, method, controls and variables are free prose, not a fixed questionnaire.
- `next_step` and `brief.unknowns` are the minimal session handoff. No execution evidence is manufactured.

```sh
agent-infra project research confirm PROJECT --revision 2 --digest sha256:ACTUAL_DIGEST --decision "User chose this proposal for further planning"
agent-infra project research export PROJECT
agent-infra project research import-notes PROJECT --section background --file notes.md --expected-revision 2 --reason "Import user's background notes"
```

Confirm requires the current revision and matching digest; old selections remain readable in history.
The decision records the caller's account of authorization, not an independently authenticated human signature.
Confirming incomplete research is allowed; execution prerequisites are checked in later stages.

Export regenerates the three managed Markdown documents only when their contents match a known generated
projection. It preserves edits and deleted files. Import-notes replaces one prose field (background,
question, or plan summary) with the complete file text and creates a revision. If importing the corresponding
managed Markdown file, its captured contents are explicitly accepted for regeneration; later edits still
cause a conflict. Use separate notes for clean imports without duplicating generated headings.

`project.yaml` and the initialization revision are separate from research revisions. Do not edit the database
or project identity to resolve conflicts. History is paginated with `--before REVISION` (exclusive, newest first).

To install this same skill into a project without changing global Agent configuration:

```sh
agent-infra project research skill PROJECT --install
```

This creates `.agents/skills/agent-infra-research/`; identical installation is repeatable, modified files
are preserved with a conflict. Without `--install`, the command returns packaged instructions as JSON.
Other Agent providers may consume the same instructions and CLI explicitly; their skill discovery is separate.

## Execute an authorized experiment through the Controller

Record the user's host/Docker choice in existing `brief.constraints`, for example
"Execution mode: host, explicitly selected by the user; results are external to Controller/Records."
This is persisted planning text, not a runtime backend selector or a machine-enforced policy.
Host mode may use the authorized local environment; do not install packages or expand resource scope
merely because the user chose host. Use the Controller workflow below only for Docker mode.
`study analysis-save` requires actual platform Run references and cannot register host-only results.

Planning save/confirm does not execute an experiment. For a platform trial, a project-local script
and report are not execution evidence: obtain actual platform Run/Job IDs and Records artifacts.
Preserve external results as external; never register a host run as if it had executed in Docker.

For a host Agent controlling a research environment, first read the bound MCP `project_context`.
Then use `environment_open` (existing Python image or validated environment_lock, approved CPU/memory),
`workspace_write` for the script and required small inputs, and `job_start` with an explicit timeout.
Read `job_logs` and `environment_status`, collect results, and call `environment_close` when finished.
Check `cleanup_complete`, `lease_released` and `archive_complete`; read durable artifacts and save an
analysis with their real IDs. A Job can fail even when the tool call succeeds. Closing MCP is not
closing the environment. If interrupted, inspect existing Runs/Jobs before starting another one.

The host project is not automatically mounted. Preserve relative paths required by the script when
copying inputs; container workdir is /workspace. Do not test the training script on the host as an
implicit substitute. Workspace writes accept UTF-8 up to 32 KiB; report larger/material transfer
requirements instead of assuming a host file is present. Do not overwrite earlier experiment results.

The same operations are available through the CLI when MCP is unavailable. Replace all uppercase
IDs/paths with actual values, use the same state directory and stable session, and capture returned IDs:

```bash
agent-infra research context --project-id PROJECT --state-dir STATE --session-id SESSION
agent-infra research open --project-id PROJECT --state-dir STATE --session-id SESSION --operation-id OPEN --image IMAGE --cpu 1 --memory-gib 2
agent-infra research write RUN code/train.py --project-id PROJECT --state-dir STATE --session-id SESSION --operation-id WRITE --file LOCAL_SCRIPT
agent-infra research start RUN --project-id PROJECT --state-dir STATE --session-id SESSION --operation-id START --timeout 120 --argv python3 code/train.py
agent-infra research logs RUN JOB --project-id PROJECT --state-dir STATE --session-id SESSION --cursor 0
agent-infra research status RUN --project-id PROJECT --state-dir STATE --session-id SESSION
agent-infra research close RUN --project-id PROJECT --state-dir STATE --session-id SESSION --operation-id CLOSE
agent-infra research artifacts RUN --project-id PROJECT --state-dir STATE --session-id SESSION
```

CPU/memory/time here are examples, not authorization. `--argv` must be last. Mutations need an
operation ID: retry the same intent with the same ID and parameters; use new IDs for new experiments.
If Controller, Docker, dependencies or access are unavailable, report that failure. Do not silently
switch to a host calculation or bypass platform admission by issuing Docker commands yourself.

For a container Agent run, use `project compile` on the adopted experiment and its execution YAML,
then `run preflight` and `run submit` with the resulting Task ID/revision and explicitly authorized
model/network/time choices. Inspect each command's `--help`; the two execution paths are alternatives,
not steps to run twice. The current entrypoints support CPU; do not infer GPU support from monitoring.

## Analyze and iterate (I batch)

A running local Controller is required. Use its state directory and project UUID:

```bash
agent-infra study analyses --project-id PROJECT --state-dir STATE
agent-infra study analysis-save --project-id PROJECT --state-dir STATE --operation-id ANALYSIS --file analysis.json
agent-infra study workflows --project-id PROJECT --state-dir STATE
agent-infra study status --project-id PROJECT --state-dir STATE --workflow-id WORKFLOW
agent-infra study step --project-id PROJECT --state-dir STATE --workflow-id WORKFLOW --task-key TASK_KEY --operation-id ROUND
```

An analysis JSON contains `results` (Run/artifact/member references with optional metric JSON pointers),
`observations`, `interpretation`, `uncertainty`, `recommendation`, and optional `supersedes` analysis ID.
Each metric has `name`, `pointer`, `unit`, `direction` (maximize/minimize/inspect); values are extracted
from the stored file. Record `data_version` and `code_version` on each result when known; do not invent
unknown versions. Failed Runs can be analyzed without an artifact. Corrections create a new analysis.

Resume from `status.actions`; retry a lost reply with the original operation ID and task key.
A task key identifies a frozen submission in `status.tasks`, not an arbitrary command. The workflow
reserves the full task timeout, including failed/interrupted attempts; it does not refund unused time.
Stop on exhausted budget or out-of-scope proposals. Describe the needed user decision instead of
creating new authorizations. The operator uses `study decide` and `study authorize` to record the
exact adopted plan and new permitted task set. Do not infer authorization from generated suggestions.

For an adopted next plan, decision JSON has `analysis_id`, `choice` (accept/modify/reject), `reason`,
`authorization` (actual user choice/source), `expected_revision`, `expected_digest`, and a full `draft`
for accept/modify. Keep the Brief unchanged; use a new experiment ID for a new experiment.
Compilation then uses the existing `project compile` command; a decision does not execute anything.
