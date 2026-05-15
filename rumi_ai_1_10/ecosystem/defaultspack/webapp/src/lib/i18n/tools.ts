export const toolMessages = {
  ja: {
    "tools.assist.auto": "Auto: 関連する tool を推薦",
    "tools.assist.all": "All tools: すべての tool を入力へ入れる",
    "tools.assist.off": "Off: 手動選択した tool だけ",
    "tools.assist.help": "入力文と tool/MCP/skill metadata を照合し、関連度が高い tool を AI に推薦します。",
  },
  en: {
    "tools.assist.auto": "Auto: recommend relevant tools",
    "tools.assist.all": "All tools: expose every tool",
    "tools.assist.off": "Off: only manually selected tools",
    "tools.assist.help": "Match the user input against tool/MCP/skill metadata and recommend relevant tools to the AI.",
  },
} as const;

export type ToolMessageKey = keyof typeof toolMessages.ja;
