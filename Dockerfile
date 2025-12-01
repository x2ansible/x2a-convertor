FROM registry.access.redhat.com/ubi9/ubi:latest

RUN dnf install -y \
    python3.12 \
    python3.12-pip \
    python3.12-devel \
    git \
    wget \
    gcc \
    gcc-c++ \
    make \
    ruby \
    ruby-devel \
    && dnf clean all

# Uv is not part of ubi.
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

# Chef CLI is needed for chef agent (installed via gem for multi-arch support)
RUN gem install chef-cli --no-document
RUN gem install berkshelf

# Accept Chef licenses non-interactively
ENV CHEF_LICENSE=accept-no-persist


WORKDIR /app
COPY . /app

# Install Python dependencies
RUN uv sync

# Set entrypoint
ENTRYPOINT ["uv", "run", "python", "app.py"]
