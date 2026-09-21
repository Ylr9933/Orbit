---
name: agent-infra-research
description: Plan research in an Agent Infra project, preserve the user's host or Docker execution choice, run authorized platform experiments through MCP or CLI and analyze recorded results across sessions.
---

# Research workflow in Agent Infra

Use the existing Agent conversation, including its planning mode when useful. The platform stores
research state; it does not supply a separate reasoning loop. Read [commands](references/commands.md)
when first saving or restoring a plan. Use the same explicit state directory as project initialization.

Start with `agent-infra project research context PROJECT`. Keep the original user request intact.
Read relevant project notes and actual data descriptions before asking for information already present.
If documents disagree with stored context, surface the difference; use explicit note import when the
user wants their edits included. Do not overwrite notes to make export succeed.

Identify the next useful research decision. Ask only about missing details that change the method,
data, comparison, success criteria or budget. Other unknowns can remain in a saved draft. Prefer a
small informative experiment before a large run; respect the user's chosen methods and scope.
A manual inspection of outputs is a valid outcome for exploratory research.

Keep background and methods readable as Markdown. Structure the experiment IDs, inputs, outputs,
metric directions and resource-request references needed by subsequent execution. Preserve stable
experiment IDs when refining the same experiment. Use existing Resources YAML, not invented fields.

Label important claims as user, sourced, inference or assumption. A sourced claim needs an actual
reference that you consulted; do not fabricate papers, data paths, observations or experimental results.
The validator checks structure and local references, not whether scientific claims are true. A resource
suggestion is not an allocation or permission to run a job.

Save a coherent Brief and Plan snapshot through the CLI with the current research revision and a
short explanation of what changed. A draft may be incomplete. Record user corrections in the relevant
fields and preserve unresolved questions and the next step. If saving conflicts, reload and reconcile;
do not blindly overwrite a newer revision. Inspect the save result for projection conflicts even when
the database save succeeded.

Record confirmation only when the user adopts that exact proposal, or their existing authorization
clearly covers it; quote or describe that choice in the decision. Use the exact revision and digest.
Do not reconfirm ordinary draft saves. Confirmation selects a plan; it does not launch an experiment.
If the current Agent mode forbids writes, discuss the proposal there and save after entering a mode
that permits the requested write. Do not bypass the Agent's restrictions.

## Agree on execution mode and preserve it

Before the first experiment, use the user's explicit choice or the adopted plan's execution mode.
If neither establishes it, recommend host for a lightweight calculation using existing dependencies,
or Docker for environment isolation, dependency changes, managed jobs or a platform execution trial,
and ask the user to choose. Task simplicity is a recommendation, not permission to switch modes.
Save the choice and its source in the existing brief.constraints prose and confirm it with the plan;
do not invent a new schema field. Reuse the choice on later rounds unless the user changes it.

For host mode, execute only within the user's scope and label results as external host execution.
Current host scripts do not automatically get a platform Run, container isolation or full Records
capture. Preserve code, parameters and outputs in the project, but do not invent Run/artifact IDs or
pass local files off as platform evidence. A locally written run_manifest.json is not a Run.

For Docker mode, or an explicitly requested Docker/resource-isolation/Records trial, execute through
the Controller; do not substitute host Python, a notebook, subprocess, or manually created Docker.
Host-side planning, authoring files and calling the platform CLI remain appropriate in either mode.

Before executing, read the execution section in [commands](references/commands.md). Use the bound MCP
tools for an interactive research environment, or compile and submit a frozen Task for a container
Agent run. Preserve the adopted method, actual user authorization and resource/time limits. If the
platform cannot execute, report the concrete error; use the equivalent platform CLI if available,
but do not silently fall back to running the experiment on the host or raise its budget.

Obtain the platform run_id and job_id (for research Jobs) before claiming execution started. On
completion, read the actual outcome and archive, verify cleanup/release, and cite Run/artifact/member
references in the analysis. If records are missing, report the execution as unverified or external.

At handoff, summarize the chosen approach, remaining unknowns and next action. Use the saved context
on the next session instead of assuming the chat history is available. Do not reinitialize the project.
When results exist, read the analysis/iteration section of [commands](references/commands.md).
Separate measured values from explanations and uncertainties. Cite actual Run/artifact members; do
not rank incompatible data versions as improvements. Suggest the next informative experiment.
Use existing workflow authorization to continue only the listed frozen tasks. If a proposed method,
data or budget is outside it, save the recommendation for the user's decision. Unknown provider costs
are not zero costs. Host driver/daemon administration remains outside this skill; creating and
controlling an authorized research environment through platform tools is part of this workflow.
