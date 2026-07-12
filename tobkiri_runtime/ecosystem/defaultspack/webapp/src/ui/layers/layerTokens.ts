export const layerZ = {
  base: 0,
  panel: 10,
  localPopover: 20,
  globalOverlay: 40,
  modalBackdrop: 50,
  modal: 60,
  commandPalette: 70,
  toast: 80,
  debug: 90,
} as const;

export type LayerName = keyof typeof layerZ;

export const layerClassName: Record<LayerName, string> = {
  base: "rumi-layer-base",
  panel: "rumi-layer-panel",
  localPopover: "rumi-layer-local-popover",
  globalOverlay: "rumi-layer-global-overlay",
  modalBackdrop: "rumi-layer-modal-backdrop",
  modal: "rumi-layer-modal",
  commandPalette: "rumi-layer-command-palette",
  toast: "rumi-layer-toast",
  debug: "rumi-layer-debug",
};
