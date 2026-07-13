# Rumi Browser Host Service Pack

This pack owns typed browser session/profile/cookie/navigation/capture/download
operation descriptors. It deliberately contains no browser driver, tool, agent,
chat, or UI implementation. Calls return `host_intent` values which the core
Authority path validates and the Viewer host broker executes.

Observation and control are separate global contracts. Control never accepts a
client supplied approval flag or token. Removing this pack removes both browser
contracts while leaving the host broker and unrelated desktop capabilities intact.

Validation was not executed by the implementation agent.
Independent testing is required before merge.
