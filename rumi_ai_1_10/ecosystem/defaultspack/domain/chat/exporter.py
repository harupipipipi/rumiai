import json
import datetime


def export_markdown(conversation):
    """会話を Markdown 文字列としてエクスポートする。"""
    lines = []
    title = conversation.get("title", "Untitled")
    lines.append("# " + title)
    lines.append("")
    created_at = conversation.get("created_at", 0)
    if created_at:
        dt = datetime.datetime.fromtimestamp(created_at / 1000, tz=datetime.timezone.utc)
        lines.append("Created: " + dt.isoformat())
    lines.append("Model: " + str(conversation.get("model", "unknown")))
    lines.append("")
    lines.append("---")
    lines.append("")
    messages = conversation.get("messages", [])
    for msg in messages:
        role = msg.get("role", "unknown")
        lines.append("### " + role.capitalize())
        lines.append("")
        raw_text = msg.get("raw_text", "")
        if raw_text:
            lines.append(raw_text)
        else:
            content = msg.get("content", [])
            if isinstance(content, str):
                lines.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        lines.append(block.get("text", ""))
                    elif isinstance(block, str):
                        lines.append(block)
        lines.append("")
    return "\n".join(lines)


def export_json(conversation):
    """会話を JSON 文字列としてエクスポートする。"""
    return json.dumps(conversation, ensure_ascii=False, indent=2, default=str)
