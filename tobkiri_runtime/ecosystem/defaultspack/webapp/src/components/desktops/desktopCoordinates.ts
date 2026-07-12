export type DesktopCoordinateRect = {
  width: number;
  height: number;
};

export type DesktopPointerPoint = {
  x: number;
  y: number;
};

export type DesktopCoordinateMapping = {
  desktopX: number;
  desktopY: number;
  scale: number;
  drawnWidth: number;
  drawnHeight: number;
  offsetX: number;
  offsetY: number;
};

export function desktopObjectContainBox(
  view: DesktopCoordinateRect,
  frame: DesktopCoordinateRect,
): Omit<DesktopCoordinateMapping, "desktopX" | "desktopY"> | null {
  if (view.width <= 0 || view.height <= 0 || frame.width <= 0 || frame.height <= 0) return null;
  const scale = Math.min(view.width / frame.width, view.height / frame.height);
  const drawnWidth = frame.width * scale;
  const drawnHeight = frame.height * scale;
  return {
    scale,
    drawnWidth,
    drawnHeight,
    offsetX: (view.width - drawnWidth) / 2,
    offsetY: (view.height - drawnHeight) / 2,
  };
}

export function pointerToDesktopCoordinates(
  pointer: DesktopPointerPoint,
  view: DesktopCoordinateRect,
  frame: DesktopCoordinateRect,
): DesktopCoordinateMapping | null {
  const box = desktopObjectContainBox(view, frame);
  if (!box) return null;
  const insideX = pointer.x >= box.offsetX && pointer.x <= box.offsetX + box.drawnWidth;
  const insideY = pointer.y >= box.offsetY && pointer.y <= box.offsetY + box.drawnHeight;
  if (!insideX || !insideY) return null;
  return {
    ...box,
    desktopX: Math.round((pointer.x - box.offsetX) / box.scale),
    desktopY: Math.round((pointer.y - box.offsetY) / box.scale),
  };
}

export function desktopToViewCoordinates(
  desktop: DesktopPointerPoint,
  view: DesktopCoordinateRect,
  frame: DesktopCoordinateRect,
): DesktopPointerPoint | null {
  const box = desktopObjectContainBox(view, frame);
  if (!box) return null;
  return {
    x: box.offsetX + desktop.x * box.scale,
    y: box.offsetY + desktop.y * box.scale,
  };
}
