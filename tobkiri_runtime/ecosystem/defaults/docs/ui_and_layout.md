# Rumi AI OS Defaults UI and Layout

This document details the design principles and expectations for the UI components provided by the `defaults` pack, specifically addressing requirements for customization, drag-and-drop capability, and dynamic tool displays.

## Core UI Philosophy: Flexibility via Assets

The Rumi AI OS frontend is not a monolithic application; it is an aggregation of "assets" provided by packs. The `defaults` pack sets the standard grid and interaction model, but almost every element is replaceable.

### Asset-Based UI Registry
1.  **Frontend/Backend Separation:** The backend handles logic, flow execution, and data storage. The frontend is exclusively responsible for rendering assets registered by packs.
2.  **Asset Catalog:** Packs define UI components (like a custom chat window, a new input style, or a settings panel) in their `ecosystem.json` under an `assets` array.
3.  **UI Settings Pack:** A conceptual or literal pack (like a `settings_pack`) can be installed, which declares generic layout assets (e.g., "Full-Screen Layout", "Sidebar Overlay"). The `defaults` pack provides the baseline grid.

## Drag-and-Drop Architecture

To fulfill the requirement of arbitrary placement (e.g., placing the chat window or input field freely):

1.  **The Canvas Container:** The main UI is considered a "Canvas."
2.  **Draggable Components:** The defaults pack's core inputs and outputs (Chat Stream, Input Bar, Tool Status) are wrapped in Draggable Asset Containers.
3.  **Position Persistence:** When a user moves a component, its new `(x, y)` or `grid-area` coordinates are saved to the user's `ui_preferences.json` in their `user_data` directory. The `defaults` pack respects these coordinates upon reload.

## Dynamic Tool Display & Settings

Tools must inform the user of what the AI is currently doing.

### 1. The Tool Sidebar (Activity Log)
*   **Purpose:** The `defaults` pack includes a standard Sidebar Activity Log.
*   **Registration:** When an AI agent executes a tool (via the Flow Engine), the backend emits a UI event. The Sidebar listens for these events and displays real-time execution status (e.g., "Searching the web for 'Python libraries'...", "Reading `config.yaml`...").
*   **Visibility:** This allows users to understand the AI's current context without cluttering the main conversation stream.

### 2. Custom Tool Display (ToolDisplay Assets)
Some tools require more than just a text log (e.g., a data visualization tool, an image generator).
*   **`tooldisplay` Registration:** A tool pack can register a specific frontend asset (React component or web component) tagged as `type: tooldisplay`.
*   **Dynamic Injection:** When that tool is executed, the `defaults` pack's UI orchestrator dynamically injects this custom asset into the Active Tool Area (often a modal or a dedicated split-pane).

### 3. Tool Settings (ToolSetting Assets)
Users need to configure tools (e.g., entering API keys, setting search preferences).
*   **`toolsetting` Registration:** A tool pack provides a JSON schema or a custom UI asset for its settings.
*   **Automatic UI Generation:** By default, if only a schema is provided, the `defaults` pack automatically generates a settings form (inputs, toggles) based on the schema's types. If a custom asset is provided, that is rendered instead. This is accessible via the main Settings panel under the "Tools" category.

## Animation Standardization

To prevent visual clashes between different packs:

1.  **Animation Constants:** The `defaults` pack defines standard CSS variables for transitions (e.g., `--rumi-anim-fast: 150ms ease`, `--rumi-anim-medium: 300ms ease-in-out`).
2.  **Guidance:** Pack developers are strongly encouraged via documentation to utilize these variables for tool displays and custom UI assets to maintain a cohesive experience (統一感).

## Fallback Mechanisms

If a custom UI asset fails to load or throws an error:
1.  **Fail-Soft Rendering:** The `defaults` pack will catch the error, remove the offending component from the screen, and render a simple error boundary block, ensuring the rest of the OS (like the core chat) remains functional.
