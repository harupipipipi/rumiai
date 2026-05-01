import test from "node:test";
import assert from "node:assert/strict";

import { filterAtMentionFiles } from "./ComposerRenderer";

test("composer file mention filters string context files", () => {
  const files = ["README.md", "src/App.tsx", "docs/context.md"];

  assert.deepEqual(filterAtMentionFiles(files, "md"), ["README.md", "docs/context.md"]);
  assert.equal(typeof filterAtMentionFiles(files, "")[0], "string");
});
