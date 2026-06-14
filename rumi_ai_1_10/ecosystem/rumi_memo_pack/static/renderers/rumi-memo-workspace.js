const React = globalThis.__RUMI_REACT__;
const h = React?.createElement;

function line(label, value) {
  return h(
    "div",
    {
      style: {
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        borderBottom: "1px solid rgba(63,63,70,0.48)",
        minHeight: 42
      }
    },
    h("span", { style: { color: "#a1a1aa", fontSize: 12 } }, label),
    h("span", { style: { color: "#f4f4f5", fontSize: 12, fontWeight: 650 } }, value)
  );
}

export default function MemoWorkspace(props) {
  if (!h) return null;
  const messageCount = Array.isArray(props.messages) ? props.messages.length : 0;
  const title = props.activeConversationTitle && props.activeConversationTitle !== "新しいチャット"
    ? props.activeConversationTitle
    : "Today";

  return h(
    "section",
    {
      style: {
        display: "flex",
        minHeight: 0,
        flex: "1 1 auto",
        flexDirection: "column",
        padding: "28px",
        background: "#111114",
        color: "#f4f4f5"
      }
    },
    h(
      "header",
      {
        style: {
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 16,
          marginBottom: 22
        }
      },
      h("h1", { style: { margin: 0, fontSize: 26, fontWeight: 750, letterSpacing: 0 } }, title),
      h("span", {
        style: {
          border: "1px solid rgba(82,82,91,0.9)",
          borderRadius: 999,
          color: "#d4d4d8",
          fontSize: 12,
          padding: "5px 10px"
        }
      }, "Memo Pack")
    ),
    h(
      "div",
      {
        style: {
          display: "grid",
          gridTemplateColumns: "minmax(0,1fr) minmax(240px,320px)",
          gap: 18,
          minHeight: 0,
          flex: "1 1 auto"
        }
      },
      h(
        "article",
        {
          style: {
            border: "1px solid rgba(63,63,70,0.72)",
            borderRadius: 8,
            background: "#18181b",
            padding: 20,
            minHeight: 320
          }
        },
        h("p", { style: { margin: "0 0 14px", color: "#d4d4d8", lineHeight: 1.7 } }, "今日のメモ"),
        h("div", { style: { display: "grid", gap: 10 } },
          ["Decision log", "Open questions", "Next notes"].map((item) => h(
            "div",
            {
              key: item,
              style: {
                border: "1px solid rgba(82,82,91,0.58)",
                borderRadius: 8,
                background: "rgba(9,9,11,0.56)",
                minHeight: 54,
                padding: "13px 14px",
                fontSize: 13
              }
            },
            item
          ))
        )
      ),
      h(
        "aside",
        {
          style: {
            border: "1px solid rgba(63,63,70,0.72)",
            borderRadius: 8,
            background: "#151518",
            padding: "14px 16px",
            alignSelf: "start"
          }
        },
        line("Profile", props.selectedProfile?.name || props.selectedProfile?.id || "default"),
        line("Messages", String(messageCount)),
        line("Tools", String(Array.isArray(props.selectedToolIds) ? props.selectedToolIds.length : 0))
      )
    )
  );
}
