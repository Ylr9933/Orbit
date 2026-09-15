ARG NODE_IMAGE=node:24.18.0-bookworm-slim
FROM ${NODE_IMAGE}

ARG AGENT_NPM_PACKAGE
ARG AGENT_VERSION

RUN test -n "${AGENT_NPM_PACKAGE}" \
    && test -n "${AGENT_VERSION}" \
    && npm install --global "${AGENT_NPM_PACKAGE}@${AGENT_VERSION}" \
    && npm cache clean --force

RUN usermod --login agent --home /home/agent --move-home node \
    && groupmod --new-name agent node \
    && mkdir -p /workspace \
    && chown -R agent:agent /workspace /home/agent

USER agent
ENV HOME=/home/agent
WORKDIR /workspace

CMD ["node", "--version"]
