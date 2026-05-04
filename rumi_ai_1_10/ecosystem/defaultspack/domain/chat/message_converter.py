def convert_to_standard(rumi_messages):
    """RumiMessage のリストを StandardMessage のリストに変換する。

    StandardMessage 形式:
      {"role": str, "content": str | list}
    tool_call content block は tool_calls として分離する。
    メタデータ (usage, cost 等) は削ぎ落とす。
    """
    standard = []
    for msg in rumi_messages:
        role = msg.get("role", "user")
        content_blocks = msg.get("content", [])
        if isinstance(content_blocks, str):
            standard.append({"role": role, "content": content_blocks})
            continue
        text_parts = []
        tool_calls = []
        tool_results = []
        for block in content_blocks:
            if not isinstance(block, dict):
                text_parts.append(str(block))
                continue
            btype = block.get("type", "text")
            if btype == "text":
                text_parts.append(block.get("text", ""))
            elif btype == "image_url":
                text_parts.append(block)
            elif btype == "image" and block.get("source"):
                text_parts.append(block)
            elif btype == "tool_call":
                tool_calls.append({
                    "id": block.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": block.get("name", ""),
                        "arguments": block.get("arguments", ""),
                    },
                })
            elif btype == "tool_result":
                tool_results.append({
                    "tool_call_id": block.get("tool_call_id", ""),
                    "content": block.get("content", ""),
                })
            else:
                text_parts.append(block.get("text", str(block)))
        if role == "tool" or (not text_parts and not tool_calls and tool_results):
            for tr in tool_results:
                standard.append({
                    "role": "tool",
                    "tool_call_id": tr.get("tool_call_id", ""),
                    "content": tr.get("content", ""),
                })
            continue
        entry = {"role": role}
        if tool_calls:
            string_parts = [t for t in text_parts if isinstance(t, str) and t]
            if string_parts:
                combined = "\n".join(string_parts)
                entry["content"] = combined if combined else None
            else:
                entry["content"] = None
            entry["tool_calls"] = tool_calls
        else:
            if any(isinstance(t, dict) for t in text_parts):
                content = []
                for part in text_parts:
                    if isinstance(part, dict):
                        content.append(part)
                    elif part:
                        content.append({"type": "text", "text": part})
                entry["content"] = content
            else:
                combined = "\n".join(t for t in text_parts if t)
                entry["content"] = combined if combined else ""
        if tool_results:
            for tr in tool_results:
                standard.append(entry)
                standard.append({
                    "role": "tool",
                    "tool_call_id": tr.get("tool_call_id", ""),
                    "content": tr.get("content", ""),
                })
            continue
        standard.append(entry)
    return standard
