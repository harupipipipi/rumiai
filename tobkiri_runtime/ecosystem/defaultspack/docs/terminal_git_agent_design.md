# Terminal Git Agent Design

Terminal risk:

- low: read-only commands such as `pwd`, `ls`, `cat`, `git status`.
- medium: local test/build commands.
- high: writes, installs, chmod, rm, network, and git push.
- critical: destructive commands outside workspace or secret exfiltration patterns.

Git operations:

- status, diff, log are safe reads.
- add, commit, restore, stash require confirmation metadata.
- push requires network approval and audit.

Output is summarized for UI while raw output remains available in run history.
