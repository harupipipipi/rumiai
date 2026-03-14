"""
test_fix_crypto_utils.py - crypto_utils.compute_file_sha256 テスト

Fix D0-3: compute_file_sha256 が crypto_utils.py に正しく配置され、
capability_executor.py から利用可能であることを検証する。
"""

import hashlib
from pathlib import Path

from core_runtime.crypto_utils import compute_file_sha256


class TestComputeFileSha256:
    """compute_file_sha256 の単体テスト"""

    def test_known_content(self, tmp_path: Path):
        """既知の内容の SHA-256 が正しく計算されること"""
        content = b"hello world"
        expected = hashlib.sha256(content).hexdigest()

        file_path = tmp_path / "test.txt"
        file_path.write_bytes(content)

        result = compute_file_sha256(file_path)
        assert result == expected

    def test_empty_file(self, tmp_path: Path):
        """空ファイルの SHA-256 が正しく計算されること"""
        expected = hashlib.sha256(b"").hexdigest()

        file_path = tmp_path / "empty.txt"
        file_path.write_bytes(b"")

        result = compute_file_sha256(file_path)
        assert result == expected

    def test_large_file(self, tmp_path: Path):
        """65536 バイトを超えるファイルでもチャンク読み込みが正しく動作すること"""
        # 128KB のデータ（チャンクサイズ 65536 を超える）
        content = b"A" * (65536 * 2 + 1234)
        expected = hashlib.sha256(content).hexdigest()

        file_path = tmp_path / "large.bin"
        file_path.write_bytes(content)

        result = compute_file_sha256(file_path)
        assert result == expected

    def test_binary_content(self, tmp_path: Path):
        """バイナリデータの SHA-256 が正しく計算されること"""
        content = bytes(range(256))
        expected = hashlib.sha256(content).hexdigest()

        file_path = tmp_path / "binary.bin"
        file_path.write_bytes(content)

        result = compute_file_sha256(file_path)
        assert result == expected

    def test_return_type_is_str(self, tmp_path: Path):
        """戻り値が str 型であること"""
        file_path = tmp_path / "test.txt"
        file_path.write_bytes(b"test")

        result = compute_file_sha256(file_path)
        assert isinstance(result, str)

    def test_hex_format(self, tmp_path: Path):
        """戻り値が 64 文字の16進文字列であること"""
        file_path = tmp_path / "test.txt"
        file_path.write_bytes(b"test")

        result = compute_file_sha256(file_path)
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)


class TestCryptoUtilsImportFromExecutor:
    """capability_executor.py から crypto_utils 経由で利用可能であることの検証"""

    def test_executor_module_has_compute_file_sha256(self):
        """capability_executor モジュールに compute_file_sha256 が存在すること"""
        from core_runtime import capability_executor
        assert hasattr(capability_executor, "compute_file_sha256")
        assert callable(capability_executor.compute_file_sha256)

    def test_executor_uses_crypto_utils_function(self):
        """capability_executor の compute_file_sha256 が crypto_utils のものと同一であること"""
        from core_runtime import capability_executor
        from core_runtime.crypto_utils import compute_file_sha256 as from_crypto

        assert capability_executor.compute_file_sha256 is from_crypto
