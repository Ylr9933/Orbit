# PostTrainBench adapter (BM04)

This optional package maps one task from pinned PostTrainBench revision
`3ed1d32ff1ec1f41282be6f8ebbcec07b19fc3d1` to one atomic native training job.
The upstream runner keeps ownership of the Agent loop, public `evaluate.py` calls, training budget,
reward-hacking judges, final evaluation and native retry rules.

The default request is a model-free engineering profile. It renders the pinned native prompt,
creates a tiny checkpoint-shaped fixture, exercises judge/result parsing, freezes an immutable
content-addressed model snapshot and archives bounded evidence. It never starts an Agent, model,
GPU, Apptainer or judge service and is not a benchmark score.

Native mode is HTCondor-only. It creates a job with an operation ClassAd, records the native job
ID, queries or cancels only that ID, and refuses local execution of upstream `run_task.sh`. The
operator must provide a private upstream `.env`, an existing private model store, scheduler command
directory and a combination-specific capability claim. The scheduler must isolate assigned GPU
visibility because the pinned native final-evaluation script clears processes visible to its job.

Large `final_model/` trees are copied into the private model store, verified file by file and named
by a content digest. Records receives `model-handoff.json`, native metrics/judge verdicts and bounded
logs rather than another copy of model weights. This is filesystem-backed handoff, not object-store
replication or remote backup.

See the BM04 operation guide for the exact request fields, safety prerequisites and validation
limits.
