# Failed-run checkpoints

Opt in to saving a local Docker filesystem checkpoint when the command exits nonzero:

```bash
orbit run --image <image> --checkpoint 4 -- <command>
orbit bench run <benchmark> -t <task> -m <method> --checkpoint 4
```

Checkpoints belong to the ordinary Run lifecycle. Capture and restoration do not inspect benchmark
names, task IDs, task file formats or scorers. Benchmark jobs pass the same policy to their solve
Runs; ordinary `orbit run` tasks use the same implementation.

| Task / execution mode | Current recovery behavior |
| --- | --- |
| Local Docker, direct Codex command | Restores files and continues the saved native session; checked with a real model |
| Local Docker, direct Claude Code command | Restores files and constructs native continuation; real-model continuation not yet checked |
| Local Docker, another command | Restores files with `--command`; the application must know how to read its saved progress |
| Process backend, services, external writable mounts, live project mounts, remote execution | Not supported by this checkpoint policy |

This is opt-in failure capture followed by an explicit resume request, not automatic retry or
periodic live snapshots. Enable it before starting the Run. The stopped container must still exist
when Orbit captures it; loss of the container or host storage before capture cannot be recovered.
File restoration does not infer a script's program counter. Training programs, for example, must
save and load their own model, optimizer and iteration checkpoints to continue computation.

The number is the maximum GiB of logical writable-layer data plus copied checkpoint files. Shared
base-image layers are excluded. This is a per-checkpoint limit, not a limit on all Docker storage or
the original run records. Large outputs still need disk space; checkpoints are not automatically
expired. Deleting the original run or its bench job also deletes its checkpoint.

On failure Orbit stops the container, saves its writable layer and the `/orbit` files (including
outputs and the native Agent home), and saves a project workspace when present. It removes copied
credential files and clears injected secret variables from the checkpoint image configuration.
The image remains private to the local Docker engine; task-created files may still be sensitive.
Normal logs and declared artifacts are collected, the original container is removed, and only then
is its lease released. Checkpoint errors and size-limit failures are reported separately and do not
replace the execution result or prevent ordinary cleanup. Shared verification and hooks are skipped
on this failure path so they cannot alter the saved solve state.

Inspect availability with `orbit show <run>`, or the Run overview in Web. Restore into a new Run:

```bash
orbit resume <run> --command 'pwd; ls "$ORBIT_OUTPUT"' --wait
orbit resume <run>
```

`--command` starts the supplied command in the restored environment; restoring files does not call
a model. Without it, Orbit uses the saved native session ID to continue a direct Codex or Claude Code
command, preserving its model and effort flags. That continuation calls the model and can incur
context-input charges. Credentials are re-injected from the current auth profile; the Agent CLI is
mounted from the host as usual. Keep the same CLI version available for session compatibility.

Each continuation has a new Run ID and `parentId` pointing to its source. Checkpoint files are copied
before the new Run is queued, and its remaining execution budget excludes snapshot collection time.
Copies avoid modifying the original failure evidence. The new Run has no benchmark trial membership
and does not replace or contribute to benchmark scores. A command override also skips verification
and hooks. A source checkpoint cannot be deleted while a restored Run is queued or running.

Limitations: local Docker only; no service containers, external writable mounts or live project
mounts. Read-only mounts are referenced rather than copied and must remain available. Project
workspaces and after-phase copy inputs are saved separately from the image. Process memory, GPU
state, tmpfs, open shells and network connections are not restored; processes must restart from
their saved files. A missing container or image cannot be reconstructed by this feature. An exhausted
execution budget cannot be reset by resuming.
