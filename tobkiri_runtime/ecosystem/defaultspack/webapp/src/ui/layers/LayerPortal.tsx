import { createPortal } from "react-dom";

import { layerZ, type LayerName } from "./layerTokens";

export function LayerPortal({
  layer,
  children,
}: {
  layer: LayerName;
  children: React.ReactNode;
}) {
  let root = document.getElementById(`rumi-layer-${layer}`);
  if (!root) {
    root = document.createElement("div");
    root.id = `rumi-layer-${layer}`;
    root.style.position = "relative";
    root.style.zIndex = String(layerZ[layer]);
    document.body.appendChild(root);
  }
  return createPortal(children, root);
}
