"""
transport/cli_commands.py — Slash-command definitions and execution.

Each command is registered in COMMANDS and receives the CLISession
plus the raw argument string.
"""

COMMANDS = {}


def command(name, description, usage=None):
    """Decorator to register a slash command."""

    def decorator(func):
        COMMANDS[name] = {
            "handler": func,
            "description": description,
            "usage": usage or ("/" + name),
        }
        return func

    return decorator


# ── Commands ─────────────────────────────────────────────────


@command("help", "Show available commands")
def cmd_help(session, args):
    """Print all available slash commands."""
    from transport.cli_formatter import c, BOLD, DIM, GREEN

    lines = []
    lines.append(c(BOLD, "Available commands:"))
    lines.append("")
    for name in sorted(COMMANDS.keys()):
        info = COMMANDS[name]
        lines.append("  " + c(GREEN, info["usage"].ljust(28)) + c(DIM, info["description"]))
    lines.append("")
    lines.append(c(DIM, "Type a message without / to chat with AI."))
    return "\n".join(lines)


@command("quit", "Exit the CLI")
def cmd_quit(session, args):
    """Signal the session to exit."""
    session.should_exit = True
    return None


@command("new", "Start a new conversation", "/new [model]")
def cmd_new(session, args):
    """Create a new conversation and switch to it."""
    model = args.strip() if args.strip() else session.config.get("default_model", "stub/default")
    result = session.backend_call("create_conversation", {"model": model})
    if result and result.get("status") == "ok":
        conv = result.get("data", {})
        conv_id = conv.get("id", conv.get("conversation_id", ""))
        if conv_id:
            session.conversation_id = conv_id
            from transport.cli_formatter import print_success_message

            print_success_message("New conversation: " + conv_id[:8] + " (model: " + model + ")")
            return None
    from transport.cli_formatter import print_error_message

    err_msg = "Failed to create conversation"
    if result and result.get("status") == "error":
        err_detail = result.get("error", {})
        if isinstance(err_detail, dict):
            err_msg = err_detail.get("message", err_msg)
        elif isinstance(err_detail, str):
            err_msg = err_detail
    print_error_message(err_msg)
    return None


@command("list", "List conversations", "/list [limit]")
def cmd_list(session, args):
    """List recent conversations."""
    limit = 20
    if args.strip().isdigit():
        limit = int(args.strip())
    result = session.backend_call("list_conversations", {"limit": limit})
    if result and result.get("status") == "ok":
        data = result.get("data", {})
        conversations = data.get("conversations", [])
        if not conversations:
            return "No conversations found."
        from transport.cli_formatter import c, DIM, GREEN, CYAN, BOLD, YELLOW

        lines = []
        lines.append(c(BOLD, "Conversations:"))
        for conv in conversations:
            cid = conv.get("id", "?")
            model = conv.get("model", "?")
            created = conv.get("created_at", "?")
            marker = " " + c(YELLOW, "◀") if cid == session.conversation_id else ""
            lines.append(
                "  "
                + c(GREEN, cid[:8])
                + "  "
                + c(DIM, "model=")
                + c(CYAN, model)
                + "  "
                + c(DIM, created[:19] if len(created) >= 19 else created)
                + marker
            )
        total = data.get("total", len(conversations))
        lines.append(c(DIM, "  (" + str(total) + " total)"))
        return "\n".join(lines)
    return "Failed to list conversations."


@command("switch", "Switch to a conversation", "/switch <id-prefix>")
def cmd_switch(session, args):
    """Switch to a conversation by ID prefix."""
    prefix = args.strip()
    if not prefix:
        return "Usage: /switch <conversation-id-prefix>"
    # Try to find matching conversation
    result = session.backend_call("list_conversations", {"limit": 100})
    if result and result.get("status") == "ok":
        conversations = result.get("data", {}).get("conversations", [])
        matches = [c for c in conversations if c.get("id", "").startswith(prefix)]
        if len(matches) == 1:
            session.conversation_id = matches[0]["id"]
            from transport.cli_formatter import print_success_message

            print_success_message("Switched to " + matches[0]["id"][:8])
            return None
        elif len(matches) > 1:
            return (
                "Ambiguous prefix — matches "
                + str(len(matches))
                + " conversations. Be more specific."
            )
        else:
            return "No conversation matching '" + prefix + "'."
    return "Failed to look up conversations."


@command("model", "Change the AI model", "/model <provider/model>")
def cmd_model(session, args):
    """Change the model for future messages."""
    model = args.strip()
    if not model:
        current = session.config.get("default_model", "stub/default")
        # Also list available models
        result = session.backend_call("list_models", {})
        lines = ["Current model: " + current]
        if result and result.get("status") == "ok":
            models = result.get("data", {}).get("models", [])
            if models:
                from transport.cli_formatter import c, DIM, CYAN

                lines.append("")
                lines.append("Available models:")
                for m in models:
                    mid = m.get("id", "?")
                    mname = m.get("name", "?")
                    lines.append("  " + c(CYAN, mid) + "  " + c(DIM, mname))
        return "\n".join(lines)
    session.config["default_model"] = model
    session.save_config()
    # If there's a current conversation, update its model too
    if session.conversation_id:
        session.backend_call(
            "update_conversation",
            {
                "conversation_id": session.conversation_id,
                "updates": {"model": model},
            },
        )
    from transport.cli_formatter import print_success_message

    print_success_message("Model set to: " + model)
    return None


@command("system", "Change the system prompt", "/system <prompt text>")
def cmd_system(session, args):
    """Set or show the system prompt."""
    prompt_text = args.strip()
    if not prompt_text:
        current = session.config.get("system_prompt", "(default)")
        return "Current system prompt: " + current
    session.config["system_prompt"] = prompt_text
    session.save_config()
    from transport.cli_formatter import print_success_message

    print_success_message("System prompt updated.")
    return None


@command("config", "Show current configuration")
def cmd_config(session, args):
    """Display current CLI configuration."""
    from transport.cli_formatter import c, BOLD, DIM, CYAN

    lines = [c(BOLD, "CLI Configuration:")]
    for key, value in sorted(session.config.items()):
        lines.append("  " + c(CYAN, key) + ": " + c(DIM, str(value)))
    if session.conversation_id:
        lines.append("  " + c(CYAN, "conversation_id") + ": " + c(DIM, session.conversation_id))
    lines.append("  " + c(CYAN, "backend") + ": " + c(DIM, session.backend_mode))
    return "\n".join(lines)


@command("clear", "Clear the terminal screen")
def cmd_clear(session, args):
    """Clear the terminal screen."""
    import os as _os

    _os.system("cls" if _os.name == "nt" else "clear")
    return None


def execute_command(session, command_line):
    """Parse and execute a slash command.

    Returns a string to display, or None if nothing to print.
    Raises KeyError if the command is unknown.
    """
    parts = command_line.lstrip("/").split(None, 1)
    cmd_name = parts[0].lower() if parts else ""
    cmd_args = parts[1] if len(parts) > 1 else ""

    if cmd_name not in COMMANDS:
        raise KeyError("Unknown command: /" + cmd_name + ". Type /help for available commands.")

    handler = COMMANDS[cmd_name]["handler"]
    return handler(session, cmd_args)
