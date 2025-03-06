# Lambda container image
FROM public.ecr.aws/lambda/python:3.13

RUN cat /etc/system-release \
    && dnf upgrade --releasever=latest \
    && dnf install -y unzip  git \
    && curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" \
    && unzip awscliv2.zip \
    && ./aws/install \
    && aws --version
ENV PYTHONUTF8=1

COPY pyproject.toml poetry.toml poetry.lock ${LAMBDA_TASK_ROOT}/
RUN pip install --upgrade pip \
    && pip install poetry \
    && poetry config virtualenvs.create false \
    && poetry install --no-root --only main

COPY src/ ${LAMBDA_TASK_ROOT}/
