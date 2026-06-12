const React = globalThis.__RUMI_REACT__;
const h = React?.createElement;

const pages = [
  { id: "today", title: "Today", count: 4 },
  { id: "ideas", title: "Ideas", count: 9 },
  { id: "drafts", title: "Drafts", count: 2 },
  { id: "archive", title: "Archive", count: 18 }
];

export default function MemoNav() {
  if (!h) return null;
  return h(
    "nav",
    {
      style: {
        height: "100%",
        padding: "16px 14px",
        background: "#0d0d10",
        color: "#e4e4e7"
      }
    },
    h("div", { style: { fontSize: 13, fontWeight: 700, marginBottom: 14 } }, "Memo"),
    h(
      "div",
      { style: { display: "grid", gap: 6 } },
      pages.map((page, index) => h(
        "button",
        {
          key: page.id,
          type: "button",
          style: {
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            minHeight: 36,
            width: "100%",
            border: "1px solid " + (index === 0 ? "rgba(244,244,245,0.22)" : "rgba(63,63,70,0.62)"),
            borderRadius: 8,
            background: index === 0 ? "rgba(244,244,245,0.08)" : "rgba(24,24,27,0.72)",
            color: "#f4f4f5",
            padding: "0 10px",
            textAlign: "left"
          }
        },
        h("span", { style: { fontSize: 12, fontWeight: 600 } }, page.title),
        h("span", { style: { fontSize: 11, color: "#a1a1aa" } }, String(page.count))
      ))
    )
  );
}
