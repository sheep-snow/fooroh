# Firehose listener container
FROM public.ecr.aws/amazonlinux/amazonlinux:2023
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
COPY --from=ghcr.io/astral-sh/uv:latest /uvx /bin/uvx

WORKDIR /project
ENV UV_CACHE_DIR=/tmp/.uv_cache

RUN cat /etc/system-release \
    && yum update \
    && yum install -y unzip git \
    && curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" \
    && unzip awscliv2.zip \
    && ./aws/install \
    && aws --version

ENV PATH="/project/.venv/bin:$PATH"

# install dependencies for pillow
# RUN yum install -y gcc openssl-devel bzip2-devel libffi-devel readline-devel sqlite sqlite-devel xz xz-devel zlib-devel

COPY pyproject.toml poetry.toml poetry.lock ./
COPY src/ /project/
RUN uv python install 3.13 \
    && uvx migrate-to-uv \
    && uv sync

ENTRYPOINT [ "uv", "run" ]
CMD [ "python", "firehose/listener.py" ]