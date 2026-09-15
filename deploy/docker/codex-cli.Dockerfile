ARG NODE_IMAGE=node:24.18.0-bookworm-slim
FROM ${NODE_IMAGE}

ARG CODEX_VERSION=0.154.0

RUN npm install --global "@openai/codex@${CODEX_VERSION}" \
    && npm cache clean --force

RUN usermod --login agent --home /home/agent --move-home node \
    && groupmod --new-name agent node \
    && mkdir -p /workspace /home/agent/.codex \
    && chown -R agent:agent /workspace /home/agent

USER agent
ENV HOME=/home/agent
ENV CODEX_HOME=/home/agent/.codex
WORKDIR /workspace

CMD ["codex", "--help"]
