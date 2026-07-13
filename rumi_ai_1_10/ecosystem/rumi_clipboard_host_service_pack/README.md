# Rumi Clipboard Host Service Pack

This pack splits clipboard read and write into separately permissioned global
contracts. It only creates caller-bound HostIntents; core Authority approves the
request and the Viewer host broker remains the sole clipboard executor.

Clipboard text is bounded to 1 MiB. Client approval material is rejected and no
clipboard payload is persisted by this pack.

Validation was not executed by the implementation agent.
Independent testing is required before merge.
