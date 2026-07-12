export const toolMessages = {
  ja: {
    "tools.assist.all": "All tools: すべての tool を入力へ入れる",
    "tools.assist.vector": "Vector: 関連する tool を推薦",
    "tools.assist.auto": "Auto: always tool と関連 tool を使用",
    "tools.assist.off": "Off: 手動選択した tool だけ",
    "tools.assist.help": "既定ではすべての tool を AI に渡します。Auto は always tool を常時入れ、残りは入力文と tool/MCP/skill metadata の関連度で推薦します。",
  },
  en: {
    "tools.assist.all": "All tools: expose every tool",
    "tools.assist.vector": "Vector: recommend relevant tools",
    "tools.assist.auto": "Auto: always tools plus relevant tools",
    "tools.assist.off": "Off: only manually selected tools",
    "tools.assist.help": "Expose every tool by default. Auto always includes always-loaded tools, then recommends remaining tools by matching user input against tool/MCP/skill metadata.",
  },
} as const;

export type ToolMessageKey = keyof typeof toolMessages.ja;
