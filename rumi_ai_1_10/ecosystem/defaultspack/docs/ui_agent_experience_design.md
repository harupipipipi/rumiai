# UI Agent Experience Design

The UI is a replaceable shell built from parts.

Expected panels:

- chat
- plan
- tool calls
- file tree
- diff viewer
- terminal
- artifacts
- memory
- project settings
- approval dialog
- model selector
- compact button
- run history
- source cards

The frontend receives capability, renderer, settings, model, tool, and account metadata from catalog APIs. It should not hard-code pack internals.
