"""Frozen PAST-Bench family request; credential files are references, never contents."""

from pydantic import BaseModel, ConfigDict, Field

PAST_REVISION = "f8223517ae7491e776b69793d9f11e9d074ab42e"
PAST_VERSION = "1.0.0"
NATIVE_AGENT_VERSION = "past-f8223517ae74"
BACKEND = "past-bench-native-v1"
FEATURES = (
    "durable_operation",
    "bounded_logs",
    "process_group_cleanup",
    "wall_timeout",
    "native_evidence",
    "ordered_family",
    "paired_persistence",
    "state_branch_evidence",
)
SUPPORTED_AGENTS = ("hermes", "hermes-plus", "nanobot", "zeroclaw")
JUDGE_KEY_ENVS = (
    "ANTHROPIC_API_KEY",
    "DEEPSEEK_API_KEY",
    "KIMI_CODE_API_KEY",
    "MINIMAX_API_KEY",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "ZAI_API_KEY",
)


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: str = Field(pattern=r"^(engineering|native)$")
    checkout_root: str
    family_dir: str
    family_rel: str
    family_digest: str
    config_digest: str
    registry_digest: str
    runner_digest: str
    agent: str
    agent_profile: str = ""
    model: str
    agent_key_file: str = ""
    judge_key_file: str = ""
    judge_key_env: str = ""
    judge_model: str = ""
    sandbox_tools: bool = False
    timeout_seconds: int = Field(gt=0, le=86400)
