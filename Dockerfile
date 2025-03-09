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

# install dependencies for pillow
# RUN dnf install -y gcc openssl-devel bzip2-devel libffi-devel readline-devel sqlite sqlite-devel xz xz-devel zlib-devel

# downloads font file for jp https://github.com/notofonts/noto-cjk
# TBD to what extent i18n support
ENV FONT_DIR=${LAMBDA_TASK_ROOT}/fonts
ENV DEFAULT_FONT_FILE=NotoSansJP-Regular.otf
RUN mkdir ${LAMBDA_TASK_ROOT}/fonts \
    && curl -o ${FONT_DIR}/${DEFAULT_FONT_FILE} -LO https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/SubsetOTF/JP/${DEFAULT_FONT_FILE}

COPY pyproject.toml poetry.toml poetry.lock ${LAMBDA_TASK_ROOT}/
RUN pip install --upgrade pip \
    && pip install poetry \
    && poetry config virtualenvs.create false \
    && poetry install --no-root --only main

COPY src/ ${LAMBDA_TASK_ROOT}/
