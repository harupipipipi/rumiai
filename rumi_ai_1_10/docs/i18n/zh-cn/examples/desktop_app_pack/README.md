<!-- docs-i18n-links:start -->
[EN](../../../../examples/desktop_app_pack/README.md) | [JP](../../../ja/examples/desktop_app_pack/README.md) | [KR](../../../ko/examples/desktop_app_pack/README.md) | [CN](./README.md)
<!-- docs-i18n-links:end -->

# 桌面应用程序包

这是一个使用 Rumi AI OS 的 **desktop_app.execute** 功能的示例包。
在单独的桌面窗口 (tkinter) 中启动应用程序。

Pack还可以作为开发者可以复制和修改的模板。

---

## 目录结构

```
desktop_app_pack/
├── ecosystem.json   # Pack マニフェスト（desktop_app セクション付き）
├── app.py           # デスクトップアプリ（tkinter Hello World + Kernel API 通信）
└── README.md        # このファイル
```

---

## 什么是desktop_app.execute 功能？

`desktop_app.execute`是Rumi AI OS的核心功能，允许Packs在**独立桌面窗口**中启动应用程序。

与查看器中的前端显示不同 (`viewer:display`)：

1.`pack-shell`二进制文件自动化内核启动确认和令牌获取
2.通过环境变量与内核API通信（`RUMI_TOKEN`，`RUMI_PORT`，`RUMI_PACK_ID`）
3. 任何GUI框架都可以使用，如tkinter、Qt、Electron、Tauri等。

能力的定义在`core_runtime/core_pack/core_desktop_capability/`中。

---

## 如何使用

### 1.构建pack-shell

```bash
cd pack-shell
cargo build --release
```

### 2. 放置包

将此目录复制到`ecosystem/`：

```bash
cp -r docs/examples/desktop_app_pack/ ecosystem/desktop_app_pack/
```

### 3.启动内核

```bash
python -m rumi_ai
```

当内核启动时，它会自动扫描`ecosystem/desktop_app_pack/ecosystem.json`。

### 4.批准包

生态系统包首次需要批准（与 core_packs 不同，它们不会自动获得批准）。
请从内核 API 或管理屏幕批准该包。

### 5. 获得补助金

`desktop_app.execute` 需要获得许可。
**注意**：`desktop_app.execute` 设置为`dangerous: true`。授予批准意味着允许桌面应用程序在主机操作系统上启动任意进程。

### 6. 使用 pack-shell 启动应用程序

```bash
pack-shell run desktop_app_pack \
  --command "python app.py" \
  --working-dir /path/to/desktop_app_pack \
  --api-token "$RUMI_API_TOKEN"
```

将打开一个 tkinter 窗口，其中包含内核 API 和运行状况检查功能的连接信息。

---

## Ecosystem.json 解释

```json
{
  "pack_id": "desktop_app_pack",
  "desktop_app": {
    "command": "python app.py",
    "window": {
      "title": "Desktop App Pack",
      "width": 600,
      "height": 400
    },
    "platforms": ["darwin", "win32", "linux"]
  }
}
```

|领域 |描述 |
|-----------|------|
| `desktop_app.command`| pack-shell 启动的命令。 `--command` 作为参数传递 |
| `desktop_app.requires_api_token`| `DesktopAppManager` 是否被视为 `RUMI_API_TOKEN` 强制性的？当前状态始终保存在`true`|中
| `desktop_app.window.title`|用于快捷方式名称/窗口标题 |
| `desktop_app.window.width/height`|建议的窗口大小（在应用程序端阅读时）|
| `desktop_app.platforms`|支持的平台 |

---

## 内核API通信

`app.py` 包含与内核 API 的示例通信。

```python
import json
from urllib.request import Request, urlopen

port = os.environ.get("RUMI_PORT", "8765")
url = f"http://127.0.0.1:{port}/health"
req = Request(url, headers={"Accept": "application/json"})
with urlopen(req, timeout=5) as resp:
    data = json.loads(resp.read().decode("utf-8"))
    print(data)  # {"status": "ok"}
```

pack-shell 设置的环境变量：

|变量|描述 |
|------|------|
| `RUMI_TOKEN`|内核颁发的临时令牌 |
| `RUMI_PORT`|内核API端口号（默认：8765）|
| `RUMI_PACK_ID`|目标包 ID |

---

## 定制技巧

- **更改 GUI**：`app.py` 中的 tkinter 代码可以替换为 Qt、wxPython、Electron 等。
- **添加API调用**：您可以通过在`Authorization: Bearer`头中设置`RUMI_TOKEN`来调用内核API
- **更改命令**：您可以将`ecosystem.json`的`desktop_app.command`更改为`"node app.js"`或`"./my_binary"`
- **代币合约**：在通过`DesktopAppManager`激活之前需要`RUMI_API_TOKEN`
- **更改包名称**：请更改`ecosystem.json`的`pack_id`和`pack_identity`
- **窗口设置**：您可以更改`title`、`width`、`height`或`desktop_app.window`

---

## 相关文档

- [Pack 桌面应用程序开发指南](../../pack_desktop_app_guide.md)
- [包开发指南](../../pack-development.md)
- [多语言包开发指南](../../multilang_pack_guide.md)
- [pack-shell 自述文件](../../../../../../pack-shell/i18n/zh-cn/README.md)
