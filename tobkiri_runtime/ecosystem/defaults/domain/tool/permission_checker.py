class PermissionChecker:
    """ツール実行権限チェッカー（最小動作版: 常に許可）"""

    def check(self, tool_name, context):
        """
        ツール実行の権限を確認する。
        戻り値: bool（最小動作版では常に True）
        """
        return True
