# Solve image for ResearchClawBench: Ubuntu 22.04 with the system Python 3.10 that the RCB venvs
# (mounted read-only at their host paths) were created from, plus common build and plotting deps.
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      python3 python3-pip python3-venv python3-dev build-essential git curl ca-certificates \
      libgl1 libglib2.0-0 libgomp1 fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/* \
 && ln -s /usr/bin/python3 /usr/local/bin/python
