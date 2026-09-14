# Agent Infra

Agent Infra is an early-stage infrastructure project for running and evaluating pluggable agents across research tasks and benchmarks. It is designed to coordinate task environments, compute resources, execution, traces, artifacts, and evaluation while preserving each agent's behavior and each benchmark's native protocol.

**Current status: repository foundation (S0).** Architecture documents, development rules, and the directory scaffold are in place. Runtime services, agent integrations, frontend features, and executable tests are not implemented yet. Dependency manifests, lockfiles, and build configuration are still placeholders. See [project status](docs/project-status.md) for the current progress and next priorities.

## What we are building

- **Pluggable agents:** adapters for complete CLI agents, workflow-based agents, and lightweight custom agents. Target integrations include Codex, Claude Code, AIDE, and a reference ReAct agent.
- **Adaptable tasks:** a lightweight meta-spec that indexes native task instructions and configuration without imposing one directory layout on every benchmark.
- **Managed execution:** isolated task workspaces, Docker environments, CPU/GPU/memory allocation, cancellation, and resource cleanup.
- **Traceable evaluation:** configuration snapshots, events, original traces, artifacts, and evaluation results tied to individual runs and attempts.
- **A shared console:** resource visibility, run and trace inspection, and an interactive entrypoint for a simple agent.

These are planned capabilities, with implementation and acceptance tracked in the project overview.

## Planned operating modes

| Mode | Execution model | Intended use |
| --- | --- | --- |
| Research | An existing agent CLI uses an infra plugin or MCP entrypoint to operate a managed task container | Interactive research and long-running jobs |
| Benchmark | The platform launches the agent inside the task container, then collects outputs and invokes evaluation according to the original protocol | Repeatable task execution and batch evaluation |

Both modes share run, attempt, environment, resource, and event contracts. They retain different agent-process ownership and trace coverage. Hidden evaluation materials remain subject to the benchmark's visibility rules.

The first distributed milestone assigns independent runs to multiple nodes through Ray, with each attempt's main execution resources on one node. Multi-node execution within a single task is a later extension.

## Repository layout

```text
src/
├── agent_infra/          # Python backend, adapters, CLI, MCP, and Worker entrypoints
│   ├── domain/          # Entities and execution invariants
│   ├── contracts/       # Versioned boundary data models
│   ├── ports/           # Interfaces for external capabilities
│   ├── application/     # Run, task, tool, and evaluation workflows
│   ├── adapters/        # Agents, benchmarks, Docker, Ray, and storage
│   ├── entrypoints/     # Protocol and process entrypoints
│   └── bootstrap/       # Configuration and dependency assembly
└── web/                 # Independent frontend project
docs/                    # Architecture, project status, task records, and guides
schemas/                 # Versioned schema snapshots generated from source
tests/                   # Unit, contract, integration, and end-to-end tests
examples/                # Small task packages and usage examples
configs/                 # Versioned, non-sensitive application configuration
deploy/                  # Product images and deployment definitions
scripts/                 # Development, code generation, and CI helpers
.github/                 # Hosting-platform workflows and collaboration templates
```

The layout describes module ownership; most implementation files and supporting configuration are currently empty. Local runtime data belongs in the ignored `var/` directory or an external state directory. Empty scaffold directories that need versioning use `.gitkeep` files.

The proposed engineering baseline is a Python backend with FastAPI, a TypeScript/React frontend, Docker execution, Ray scheduling, and centralized metadata and artifact storage. Exact versions and working installation commands will be established during S0. See the [engineering design](docs/architecture/repository-architecture.md) for boundaries and tradeoffs.

## Start here

| Document | Purpose |
| --- | --- |
| [Project status](docs/project-status.md) | Current stage, delivered outcomes, gaps, and next priorities |
| [Agent development rules](AGENTS.md) | Branch isolation, scope, validation, persistence, and handoff requirements |
| [Goals and architecture](docs/architecture/Agent_Infra_目标与架构设计_v0.1.md) | Product scope and the initial system design, in Chinese |
| [Repository architecture](docs/architecture/repository-architecture.md) | Code organization, interfaces, collaboration, and stage acceptance, in Chinese |
| [Original architecture sketch](docs/architecture/arch.jpg) | The source sketch behind the initial design |

There is no supported application installation or launch procedure yet. Before using a command from a design document, check that its implementation and configuration exist. In particular, the proposed `make` targets are not executable project workflows at this stage.

## Development workflow

1. Read `AGENTS.md`, the project overview, and the relevant task record and architecture sections.
2. Work on a task branch. Use separate worktrees for concurrent editing tasks; keep `main` read-only for development.
3. Implement within the agreed module boundaries and validate the actual change with appropriate checks.
4. Update `docs/changes/<task-id>.md` for significant work. Update `docs/project-status.md` when overall capabilities, milestones, or priorities change.
5. Include implementation, its record, and any required overview update in the same PR. Follow the established authorization, review, and integration rules.

The project overview is a concise current-state summary. Task records preserve recovery context and evidence for individual changes. Git and PR history establish whether those changes have been integrated.

The [ignore policy](.gitignore) excludes local environments, caches, credentials, runtime data, and build output while keeping shared configuration, dependency locks, schemas, and small fixtures available for version control.

## Roadmap

| Stage | Acceptance focus |
| --- | --- |
| S0 | A versioned repository with working installation, checks, and builds |
| S1 | Core contracts, fake implementations, and two differently structured task examples |
| S2 | Complete single-node research and benchmark workflows with artifacts and cleanup |
| S3 | Verified two-node scheduling, resource accounting, and failure handling |
| S4 | Resource, trace, and chat pages plus protocol-correct batch evaluation and export |

Detailed acceptance criteria are in the architecture documents. Future extensions include more adapters, remote subjobs, multi-node execution, and checkpoint-based recovery.

## License

License selection is pending; `LICENSE` is currently an empty placeholder.
