# Build with scripts/dev/build_codex_research_image.py. No credentials in build context.
ARG PYTHON_IMAGE=python:3.12-slim
FROM ${PYTHON_IMAGE}
ARG CODEX_VERSION=0.154.0
LABEL agent-infra.provider="codex" agent-infra.codex.version="${CODEX_VERSION}"
COPY codex-package/ /opt/codex/
ENV PATH="/opt/codex/bin:/opt/codex/codex-path:${PATH}"
ENV HOME=/home/agent
WORKDIR /workspace
CMD ["codex", "--version"]
