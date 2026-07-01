const REACT_ELEMENT_TYPE = Symbol.for("react.transitional.element");

function h(type, props, ...children) {
  const normalizedProps = { ...(props || {}) };
  const key = normalizedProps.key == null ? null : String(normalizedProps.key);
  const ref = normalizedProps.ref ?? null;
  delete normalizedProps.key;
  delete normalizedProps.ref;
  if (children.length === 1) {
    normalizedProps.children = children[0];
  } else if (children.length > 1) {
    normalizedProps.children = children;
  }
  return {
    $$typeof: REACT_ELEMENT_TYPE,
    type,
    key,
    props: normalizedProps,
    _owner: null,
    ref,
    _store: {}
  };
}

const pages = [
  { id: "today", title: "Today", count: 4 },
  { id: "ideas", title: "Ideas", count: 9 },
  { id: "drafts", title: "Drafts", count: 2 },
  { id: "archive", title: "Archive", count: 18 }
];

export default function MemoNav() {
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
