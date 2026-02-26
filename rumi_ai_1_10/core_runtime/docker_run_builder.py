"""
docker_run_builder.py - Docker run コマンド引数リスト生成 (Builder パターン)

python_file_executor.py と secure_executor.py で重複していた
Docker コンテナ起動コマンドのセキュリティベースラインを共通化する。

build() は List[str] を返すだけであり、subprocess の呼び出し方法には関与しない。

セキュリティベースライン (デフォルト):
  --rm, --network=none, --cap-drop=ALL,
  --security-opt=no-new-privileges:true, --read-only,
  --dns=127.0.0.1 (--network=none 時のみ / Defense-in-Depth),
  --tmpfs=/tmp:size=64m,noexec,nosuid,
  --memory=256m, --memory-swap=256m, --cpus=0.5,
  --user=65534:65534
"""

from __future__ import annotations

from typing import List, Optional


class DockerRunBuilder:
    """
    Docker run コマンド引数リストを構築する Builder。

    Usage::

        cmd = (
            DockerRunBuilder(name="my-container")
            .pids_limit(100)
            .volume("/host/path:/container/path:ro")
            .env("KEY", "VALUE")
            .label("rumi.managed", "true")
            .image("python:3.11-slim")
            .command(["python", "/executor.py", "main.py"])
            .build()
        )
        # cmd は List[str]: ["docker", "run", "--rm", "--name", "my-container", ...]
    """

    # セキュリティベースライン定数
    DEFAULT_MEMORY = "256m"
    DEFAULT_MEMORY_SWAP = "256m"
    DEFAULT_CPUS = "0.5"
    DEFAULT_PIDS_LIMIT = 50
    DEFAULT_USER = "65534:65534"
    DEFAULT_NETWORK = "none"
    DEFAULT_TMPFS = "/tmp:size=64m,noexec,nosuid"

    def __init__(self, name: str) -> None:
        self._name: str = name
        self._pids_limit_val: int = self.DEFAULT_PIDS_LIMIT
        self._user: str = self.DEFAULT_USER
        self._network: str = self.DEFAULT_NETWORK
        self._ulimits: List[str] = []
        self._volumes: List[str] = []
        self._envs: List[List[str]] = []
        self._group_adds: List[int] = []
        self._workdir_val: Optional[str] = None
        self._labels: List[List[str]] = []
        self._image_val: Optional[str] = None
        self._command_val: List[str] = []

    # ---- Safety guards (L-13) ----

    def __iter__(self):
        raise TypeError(
            "DockerRunBuilder is not iterable. "
            "Did you forget to call .build()? "
            "Use: subprocess.run(builder.build(), ...)"
        )

    def __str__(self):
        return "<DockerRunBuilder: call .build() to get command list>"

    # ---- パラメータ設定 (メソッドチェーン対応) ----

    def network(self, net: str) -> "DockerRunBuilder":
        """--network を設定 (デフォルト: none)"""
        self._network = net
        return self

    def pids_limit(self, limit: int) -> "DockerRunBuilder":
        """--pids-limit を設定 (デフォルト: 50)"""
        self._pids_limit_val = limit
        return self

    def user(self, user: str) -> "DockerRunBuilder":
        """--user を設定 (デフォルト: 65534:65534)"""
        self._user = user
        return self

    def ulimit(self, spec: str) -> "DockerRunBuilder":
        """--ulimit を追加 (例: "nproc=50:50")"""
        self._ulimits.append(spec)
        return self

    def volume(self, mount_spec: str) -> "DockerRunBuilder":
        """-v マウントを追加 (例: "/host:/container:ro")"""
        self._volumes.append(mount_spec)
        return self

    def secret_file(self, host_path: str, container_path: str) -> "DockerRunBuilder":
        """Secret ファイルを読み取り専用でマウントする。

        ホスト側は一時ファイル（0o600）、コンテナ側は /run/secrets/<name>:ro を想定。
        環境変数ではなくファイルマウントを使う（docker inspect / /proc 経由の漏洩防止）。
        """
        self._volumes.append(f"{host_path}:{container_path}:ro")
        return self

    def env(self, key: str, value: str) -> "DockerRunBuilder":
        """-e 環境変数を追加"""
        self._envs.append([key, value])
        return self

    def group_add(self, gid: int) -> "DockerRunBuilder":
        """--group-add を追加"""
        self._group_adds.append(gid)
        return self

    def workdir(self, path: str) -> "DockerRunBuilder":
        """-w ワーキングディレクトリを設定"""
        self._workdir_val = path
        return self

    def label(self, key: str, value: str) -> "DockerRunBuilder":
        """--label を追加"""
        self._labels.append([key, value])
        return self

    def image(self, img: str) -> "DockerRunBuilder":
        """Docker イメージを設定"""
        self._image_val = img
        return self

    def command(self, cmd: List[str]) -> "DockerRunBuilder":
        """コンテナ内で実行するコマンドを設定"""
        self._command_val = list(cmd)
        return self

    # ---- ビルド ----

    def build(self) -> List[str]:
        """
        docker run コマンド引数リストを生成して返す。

        出力順序:
          docker run --rm --name {name}
          セキュリティベースライン
          --pids-limit {n}
          --user {user}
          [--ulimit ...]
          [-v ...]
          [-e ...]
          [--group-add ...]
          [-w ...]
          [--label ...]
          {image}
          {command...}

        Raises:
            ValueError: image が未設定の場合
        """
        if not self._image_val:
            raise ValueError("image is required: call .image('python:3.11-slim') before .build()")

        cmd: List[str] = [
            "docker", "run",
            "--rm",
            "--name", self._name,
            # --- セキュリティベースライン ---
            f"--network={self._network}",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            "--read-only",
        ]

        # M-11: DNS リーク防御 (Defense-in-Depth)
        # --network=none 時のみ内部 DNS を明示指定し、万一の DNS リークを防ぐ
        if self._network == "none":
            cmd.append("--dns=127.0.0.1")

        cmd.extend([
            f"--tmpfs={self.DEFAULT_TMPFS}",
            f"--memory={self.DEFAULT_MEMORY}",
            f"--memory-swap={self.DEFAULT_MEMORY_SWAP}",
            f"--cpus={self.DEFAULT_CPUS}",
            f"--pids-limit={self._pids_limit_val}",
            f"--user={self._user}",
        ])

        # ulimits
        for spec in self._ulimits:
            cmd.append(f"--ulimit={spec}")

        # volumes
        for mount_spec in self._volumes:
            cmd.extend(["-v", mount_spec])

        # envs
        for key, value in self._envs:
            cmd.extend(["-e", f"{key}={value}"])

        # group-adds
        for gid in self._group_adds:
            cmd.extend(["--group-add", str(gid)])

        # workdir
        if self._workdir_val is not None:
            cmd.extend(["-w", self._workdir_val])

        # labels
        for key, value in self._labels:
            cmd.extend(["--label", f"{key}={value}"])

        # image + command
        cmd.append(self._image_val)
        cmd.extend(self._command_val)

        return cmd
