---
name: agent-infra-research
description: Develop or revise a research question and experiment plan with the user in an Agent Infra project, analyze recorded results, preserve decisions and resume authorized experiments across sessions using the project CLI.
---

# Research planning in Agent Infra

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

At handoff, summarize the chosen approach, remaining unknowns and next action. Use the saved context
on the next session instead of assuming the chat history is available. Do not reinitialize the project.
When results exist, read the analysis/iteration section of [commands](references/commands.md).
Separate measured values from explanations and uncertainties. Cite actual Run/artifact members; do
not rank incompatible data versions as improvements. Suggest the next informative experiment.
Use existing workflow authorization to continue only the listed frozen tasks. If a proposed method,
data or budget is outside it, save the recommendation for the user's decision. Unknown provider costs
are not zero costs. Container/runtime administration remains outside this skill.
