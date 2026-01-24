# Rumi AI Pack: default
#
# このイメージは default Pack 専用。
# 完全に隔離され、他の Pack とは共有しない。

FROM rumi-base:latest

LABEL rumi.pack_id="default"
LABEL rumi.managed="true"

USER root

# この Pack 専用の venv
RUN python -m venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
ENV VIRTUAL_ENV="/app/.venv"

# pip アップグレード
RUN pip install --no-cache-dir --upgrade pip

# この Pack のコード
COPY . /app/pack/

# 権限設定
RUN chown -R rumi:rumi /app /sandbox

# 実行ユーザー
USER rumi

# 環境変数
ENV PACK_ID="default"
ENV SANDBOX_PATH="/sandbox"

WORKDIR /app/pack

CMD ["tail", "-f", "/dev/null"]
