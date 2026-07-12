# Tobkiri Launcher app identity migration

Phase 3D changes the desktop bundle identifier from `dev.rumiai.app` to
`dev.tobkiri.launcher`. On first launch, when the new application-data directory
does not exist, the launcher copies the legacy directory through a sibling
staging directory and atomically renames it into place. The legacy directory is
retained. Existing new data always wins, repeated launches are no-ops, and
symbolic links cause migration to fail closed.

macOS privacy permissions are bound to application identity and are deliberately
not copied. Users may need to grant screen recording, accessibility, microphone,
or related permissions again in System Settings.
