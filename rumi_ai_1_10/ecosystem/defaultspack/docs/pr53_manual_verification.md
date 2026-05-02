# PR #53 Follow-up Manual Verification

Use the browser UI after starting the defaultspack webapp.

- Narrow width and normal width: the composer `+` menu opens, stays within the viewport, and closes from the backdrop.
- File attachment: selecting a file adds an attachment chip in the composer.
- Slash command: typing `/coding` switches into the coding flow/mode when that command is available.
- Coding footer: branch, workspace root, and selected files are visible in the coding footer.
- Sidebar drag/drop: dragging a sidebar tool that declares `ui.drop_capabilities: ["composer.toggle_chip"]` onto the composer creates or toggles the tool chip.
