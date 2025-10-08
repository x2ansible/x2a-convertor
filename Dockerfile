FROM registry.access.redhat.com/ubi9/ubi:latest

RUN dnf install -y \
    python3.12 \
    python3.12-pip \
    python3.12-devel \
    git \
    wget \
    gcc \
    make \
    && dnf clean all

# Uv is not part of ubi.
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

# Chef CLI is needed for chef agent
RUN curl -L https://omnitruck.chef.io/install.sh | bash -s -- -P chef-workstation


WORKDIR /app
COPY . /app

# Install Python dependencies
RUN uv sync

# Set entrypoint
ENTRYPOINT ["uv", "run", "python", "app.py"]
