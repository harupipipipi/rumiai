import test from "node:test";
import assert from "node:assert/strict";
import {
  TYPE_SPECIMEN_CASES,
  createRenderJobs,
  createRenderMatrix,
  createSourceAttribute,
  createTypeSpecimenManifest,
} from "../src/index.mjs";
import { defineRumiFrontend } from "../../rumi-ui-contracts/src/index.mjs";

test("render matrix spans viewport, text scale, and scenario dimensions", () => {
  const config = defineRumiFrontend({
    viewports: [390, 768],
    textScales: [1, 2],
    scenarios: ["default", "long"],
  });

  assert.equal(createRenderMatrix(config).length, 8);
});

test("candidate render jobs carry required Rumi DOM attributes", () => {
  const [job] = createRenderJobs(
    { id: "candidate-a", previewUrl: "/preview/reply-composer" },
    { id: "reply-composer", density: "comfortable" },
    defineRumiFrontend({ viewports: [390], textScales: [1], scenarios: ["default"] }),
  );

  assert.equal(job.requiredAttributes["data-rumi-node"], "reply-composer");
  assert.equal(job.outputPath, ".rumi/ui/renders/reply-composer/candidate-a/reply-composer__candidate-a__w390__t1__default.png");
});

test("type specimen manifest includes Japanese and numeric stress cases", () => {
  const manifest = createTypeSpecimenManifest("foundation-a");
  assert.deepEqual(manifest.viewports, [390, 768, 1440]);
  assert.ok(TYPE_SPECIMEN_CASES.some((item) => item.id === "long-ja-heading"));
  assert.ok(TYPE_SPECIMEN_CASES.some((item) => item.id === "date-money"));
});

test("source attributes are stable file-line markers", () => {
  assert.equal(createSourceAttribute("src/features/inbox/ReplyComposer.tsx", 42), "src/features/inbox/ReplyComposer.tsx:42");
});
