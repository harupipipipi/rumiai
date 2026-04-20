# Rumi AI OS Defaults Profiles and Models

This document details how the `defaults` pack manages AI profiles, tool configurations, and user data to fulfill the requirements for extreme flexibility, custom instructions, and advanced model orchestration (like Mixture of Agents).

## The Principle of "Anything Goes" Profiles

The traditional approach is to rigidly define an `AI Profile` (e.g., just `model_name` and `temperature`). Rumi AI OS adopts a flexible, schema-less approach for the core profile object, allowing packs to inject whatever they need.

### 1. Flexible AI Profiles
*   **Structure:** An AI profile (stored in `user_data/ai_profiles/`) is a JSON object. While the `defaults` pack requires standard fields like `id`, `name`, and `provider`, the rest is open.
*   **Custom Instructions:** Users or packs can add fields like:
    ```json
    {
      "id": "coding_assistant",
      "provider": "openai",
      "model": "gpt-4",
      "system_prompt": "You are a helpful coding assistant.",
      "user_preferences": {
        "language_requirement": "English Recommended",
        "output_format": "markdown",
        "verbosity": "concise"
      },
      "custom_pack_data": {
        "my_pack_id": {
          "special_feature_enabled": true
        }
      }
    }
    ```
*   **Interpretation:** The `defaults` pack's prompt builder reads these `user_preferences` and dynamically injects them into the final system prompt context before sending it to the LLM.

### 2. Standardizing User Data
All configuration related to a specific user's environment must be stored under `user_data/`. This includes:
*   `user_data/ai_profiles/`
*   `user_data/tool_settings/`
*   `user_data/agent_configs/`
*   `user_data/ui_preferences/`

This standardization ensures that user configurations are portable, easily backed up, and isolated from system-level pack files.

## Advanced Model Support (MoA, Ensembles, etc.)

To support concepts like Mixture of Agents (MoA) or custom routing architectures, the `defaults` pack must not assume a 1:1 relationship between an Agent and a single Model.

### 1. The "Virtual Provider" Concept
Instead of modifying the core engine to support MoA, the `defaults` pack encourages the creation of "Virtual Providers".
*   **Implementation:** A pack can register a new AI Provider (e.g., `provider: moa_router`). To the `defaults` pack Agent, this looks like any other LLM.
*   **Delegation:** When the Agent sends a message to `moa_router`, the `moa_router` pack's backend handler takes over. It can then spawn sub-requests to various actual models (GPT-4, Claude, etc.), synthesize the results (the MoA process), and return the final response back to the Agent.

### 2. Multi-Model Agents
Alternatively, the `defaults` pack's `agent.json` schema allows specifying a primary model, and an optional **Fallback Model** or a specific model for **Planning/Reasoning** vs. **Tool Execution**.

```json
{
  ...
  "models": {
    "primary": "anthropic/claude-3-opus",
    "fallback": "openai/gpt-3.5-turbo",
    "planner": "openai/gpt-4"
  },
  ...
}
```
This enables the built-in agents to be highly robust and cost-effective without needing specialized MoA packs for basic diverse model usage.
