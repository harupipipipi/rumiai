export const toolMessages = {
  ja: {
    "tools.assist.all": "All tools: すべての tool を入力へ入れる",
    "tools.assist.vector": "Vector: 関連する tool を推薦",
    "tools.assist.auto": "Vector: 関連する tool を推薦",
    "tools.assist.off": "Off: 手動選択した tool だけ",
    "tools.assist.help": "既定ではすべての tool を AI に渡します。Vector は入力文と tool/MCP/skill metadata を照合し、関連度が高い tool だけを推薦します。",
  },
  en: {
    "tools.assist.all": "All tools: expose every tool",
    "tools.assist.vector": "Vector: recommend relevant tools",
    "tools.assist.auto": "Vector: recommend relevant tools",
    "tools.assist.off": "Off: only manually selected tools",
    "tools.assist.help": "Expose every tool by default. Vector matches user input against tool/MCP/skill metadata and recommends only relevant tools.",
  },
} as const;

export type ToolMessageKey = keyof typeof toolMessages.ja;
