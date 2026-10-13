# PostTrainBench solve/verify image.
#
# Two stages: the builder installs every Python package from the wheels that
# fetch-wheels.sh downloaded plus PyPI, and the runtime stage copies only the
# resulting site-packages. The wheels themselves never ship in the final image.
#
# Mirror arguments default to the Chinese mirrors, which are the fastest from
# where this was developed. Override them elsewhere:
#   docker build --build-arg APT_MIRROR=deb.debian.org \
#                --build-arg PIP_INDEX_URL=https://pypi.org/simple \
#                -t orbit-local/ptb-solve:latest .

# ---- builder: install all Python packages ----
FROM python:3.12-slim AS builder

ARG APT_MIRROR=mirrors.aliyun.com
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1

RUN if [ "$APT_MIRROR" != "deb.debian.org" ]; then \
      sed -i "s|deb.debian.org|$APT_MIRROR|g" /etc/apt/sources.list.d/debian.sources; \
    fi

# flash-attn compiles at install time and needs a toolchain.
RUN apt-get update && apt-get install -y --no-install-recommends \
      git wget curl build-essential ca-certificates \
      libgl1 libglib2.0-0 libgomp1 libnuma1 libffi-dev \
      libxml2 libxml2-dev libxslt1-dev \
 && rm -rf /var/lib/apt/lists/*

# torch and vllm come from the pre-downloaded wheels, so the container needs no
# network for the two largest dependencies.
COPY wheels/torch-2.13.0+cu130-cp312-cp312-manylinux_2_28_x86_64.whl /tmp/wheels/
COPY wheels/vllm-deps/ /tmp/wheels/
RUN pip install --no-cache-dir --no-index --find-links=/tmp/wheels \
      /tmp/wheels/torch-2.13.0+cu130-cp312-cp312-manylinux_2_28_x86_64.whl \
 && pip install --no-cache-dir --no-index --find-links=/tmp/wheels vllm \
 && rm -rf /tmp/wheels

# flash-attn builds from source; --no-build-isolation lets it see torch.
RUN pip install --no-cache-dir flash-attn==2.8.3 --no-build-isolation \
      --index-url "$PIP_INDEX_URL" \
      --timeout 1000 --retries 20

# The dependency list PostTrainBench pins in containers/standard.def.
COPY requirements-direct.txt /opt/requirements-direct.txt
RUN pip install --no-cache-dir -r /opt/requirements-direct.txt \
      --index-url "$PIP_INDEX_URL" \
      --timeout 1000 --retries 20

# inspect_evals from source at the commit PostTrainBench's evaluate.py expects.
RUN mkdir -p /opt && cd /opt \
 && git clone https://github.com/UKGovernmentBEIS/inspect_evals.git \
 && cd /opt/inspect_evals \
 && git checkout 06001a83e6d7c709c2ede0570dce7f1031a0bad8 \
 && pip install --no-cache-dir .

# ---- runtime: site-packages plus the libraries the packages load ----
FROM python:3.12-slim

ARG APT_MIRROR=mirrors.aliyun.com

ENV DEBIAN_FRONTEND=noninteractive \
    NO_PROXY=localhost,127.0.0.1 \
    no_proxy=localhost,127.0.0.1 \
    PIP_NO_CACHE_DIR=1

RUN if [ "$APT_MIRROR" != "deb.debian.org" ]; then \
      sed -i "s|deb.debian.org|$APT_MIRROR|g" /etc/apt/sources.list.d/debian.sources; \
    fi

# Runtime libraries only; the compiler toolchain stays in the builder.
RUN apt-get update && apt-get install -y --no-install-recommends \
      git curl ca-certificates \
      libgl1 libglib2.0-0 libgomp1 libnuma1 libffi-dev \
      libxml2 libxslt1-dev \
 && rm -rf /var/lib/apt/lists/*

# Node 22 for the Codex CLI the reward-hacking judges use.
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /opt/inspect_evals /opt/inspect_evals

RUN npm install -g @openai/codex@0.137.0

WORKDIR /task
