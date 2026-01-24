# Rumi AI Sandbox Base Image
# 
# このイメージは全 Pack で共有される信頼できるベース。
# Pack のコードは一切含まない。

FROM python:3.11-alpine

LABEL maintainer="Rumi AI"
LABEL description="Rumi AI Sandbox Base Image"

# 基本パッケージ（公式が提供、信頼できる）
RUN apk add --no-cache \
    git \
    curl \
    build-base \
    libffi-dev \
    openssl-dev

# 作業ディレクトリ
WORKDIR /app

# サンドボックス用ディレクトリ
RUN mkdir -p /sandbox && chmod 755 /sandbox

# 非root ユーザー
RUN adduser -D -u 1000 rumi
RUN chown -R rumi:rumi /app /sandbox

# デフォルトユーザー
USER rumi

# ヘルスチェック用
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s \
    CMD python -c "print('healthy')" || exit 1

CMD ["tail", "-f", "/dev/null"]
