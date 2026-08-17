FROM registry.access.redhat.com/ubi10/ubi:latest

RUN dnf install -y \
    python3.12 \
    python3.12-pip \
    python3.12-devel \
    git \
    wget \
    gcc \
    gcc-c++ \
    make \
    cmake \
    ruby \
    ruby-devel \
    libffi-devel \
    libyaml-devel \
    && dnf clean all

RUN python3.12 -m pip install --no-cache-dir uv  # installs to /usr/local/bin, already on PATH

# Chef CLI is needed for chef agent (installed via gem for multi-arch support)
RUN gem install chef-cli --no-document
RUN gem install berkshelf
RUN gem install r10k --no-document

# Accept Chef licenses non-interactively
ENV CHEF_LICENSE=accept-no-persist


WORKDIR /app
COPY . /app

# Install Python dependencies
RUN uv sync

# Set entrypoint
ENTRYPOINT ["uv", "run", "python", "app.py"]
