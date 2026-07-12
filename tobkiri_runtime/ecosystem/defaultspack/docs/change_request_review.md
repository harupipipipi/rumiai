# Rumi Review Phase 1

Rumi Review is the defaultspack read-only review shell for local workspace
changes. The user-facing UI name is **Rumi Review**. The internal API and
storage name is `change_request`.

This feature must not use PR terminology. A change request is a local review
record for the current working tree. It is not a GitHub object, it does not
imply a branch publication, and Phase 1 intentionally does not include commit
or push.

## Phase 1 Scope

Phase 1 captures and presents a read-only snapshot of a local working tree:

- create and list local `change_request` review records;
- snapshot modified, staged, deleted, and untracked files;
- synthesize unified diffs for untracked files as new-file diffs;
- compute a working tree hash for the snapshot;
- report stale review state when the current working tree no longer matches the
  captured snapshot;
- store review metadata outside the reviewed repository.

Phase 1 does not write into the reviewed workspace. In particular, it must not
create `.rumi_review`, `.rumi_reviews`, `.rumi_change_requests`, or equivalent
metadata inside the target repo. The store belongs in defaultspack runtime data,
for example under the configured `RUMI_DEFAULTSPACK_CHANGE_REQUEST_STORE_PATH`.
The default UI, HTTP route set, and function registry do not expose commit
controls, `POST /api/change-requests/{id}/commit`, or
`coding_change_request_commit`.

## Diff Seal

Each change request includes a Diff Seal: the snapshot identity that binds the
review to the files and content that were visible when the review was created.
At minimum, the seal records:

- the reviewed workspace root;
- the captured file list and per-file status;
- the unified diffs shown to the reviewer;
- a `working_tree_hash` for the captured state.

Untracked files must be represented with synthetic new-file diffs, using the
normal unified diff shape:

```diff
diff --git a/path.txt b/path.txt
new file mode 100644
--- /dev/null
+++ b/path.txt
@@
+new content
```

The synthetic diff lets the UI render untracked files in the same review surface
as modified tracked files without staging or mutating the repo.

## Stale Review Warning

Rumi Review should compare the current working tree hash with the Diff Seal hash
before presenting or acting on a review. If the hashes differ, the UI should show
a stale review warning and ask the user to refresh or recreate the review before
trusting the displayed diff.

The stale warning means: "the review snapshot no longer matches your working
tree." It is not an approval, denial, merge decision, or permission grant.

## API Shape

The Phase 1 backend uses `change_request` internally and exposes basic local API
routes under `/api/change-requests` when the backend is available:

- `GET /api/change-requests` lists local review records.
- `POST /api/change-requests` creates a read-only review record for a workspace.
- `GET /api/change-requests/{id}` returns one review record and its stale state.

Route handlers, block modules, function names, and store identifiers should use
`change_request`. They should avoid PR-shaped aliases and related route names.

## Why Commit And Push Are Out Of Phase 1

Commit and push remain intentionally out of scope for Phase 1 because Rumi
Review is only a local read-only review shell. Turning a review into Git history
or publishing it to a remote requires separate approval-aware flows, audit
entries, and policy checks. Keeping Phase 1 read-only makes it safe to open a
review without granting write capability, network access, or Git publication
authority.

Experimental local commit plumbing may be enabled explicitly with
`RUMI_REVIEW_ENABLE_COMMIT=1` on the backend and
`VITE_RUMI_REVIEW_ENABLE_COMMIT=1` in the web build. Those flags are
default-off and are outside the Phase 1 default surface.
