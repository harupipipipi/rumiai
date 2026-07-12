import test from "node:test";
import assert from "node:assert/strict";

import { desktopObjectContainBox, desktopToViewCoordinates, pointerToDesktopCoordinates } from "./desktopCoordinates";

test("pointerToDesktopCoordinates maps object-contain letterboxed coordinates", () => {
  const mapped = pointerToDesktopCoordinates(
    { x: 400, y: 300 },
    { width: 800, height: 600 },
    { width: 1600, height: 900 },
  );

  assert.deepEqual(mapped && {
    desktopX: mapped.desktopX,
    desktopY: mapped.desktopY,
    scale: mapped.scale,
    offsetY: mapped.offsetY,
  }, {
    desktopX: 800,
    desktopY: 450,
    scale: 0.5,
    offsetY: 75,
  });
});

test("pointerToDesktopCoordinates rejects clicks outside the drawn frame", () => {
  assert.equal(pointerToDesktopCoordinates(
    { x: 400, y: 20 },
    { width: 800, height: 600 },
    { width: 1600, height: 900 },
  ), null);

  assert.equal(pointerToDesktopCoordinates(
    { x: 0, y: 300 },
    { width: 0, height: 600 },
    { width: 1600, height: 900 },
  ), null);
});

test("desktopToViewCoordinates uses the same contain box as pointer mapping", () => {
  const box = desktopObjectContainBox(
    { width: 800, height: 600 },
    { width: 1600, height: 900 },
  );
  const viewPoint = desktopToViewCoordinates(
    { x: 1600, y: 900 },
    { width: 800, height: 600 },
    { width: 1600, height: 900 },
  );

  assert.deepEqual(box && {
    drawnWidth: box.drawnWidth,
    drawnHeight: box.drawnHeight,
    offsetX: box.offsetX,
    offsetY: box.offsetY,
  }, {
    drawnWidth: 800,
    drawnHeight: 450,
    offsetX: 0,
    offsetY: 75,
  });
  assert.deepEqual(viewPoint, { x: 800, y: 525 });
});
