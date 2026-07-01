from __future__ import annotations

from typing import Any


PACK_ID = "rumi_workspace_surfaces"


SURFACES = {
    "write": {
        "title": "Write",
        "kind": "write",
        "renderer": "rumi_workspace_surfaces.write",
        "initial_text": "# Draft\n\n",
    },
    "image": {
        "title": "Image",
        "kind": "image",
        "renderer": "rumi_workspace_surfaces.image",
        "initial_text": "Image notes\n",
    },
    "slide": {
        "title": "Slide",
        "kind": "slide",
        "renderer": "rumi_workspace_surfaces.slide",
        "initial_text": "# Slide 1\n\nSpeaker notes...\n",
    },
    "movie": {
        "title": "Movie",
        "kind": "movie",
        "renderer": "rumi_workspace_surfaces.movie",
        "initial_text": "Timeline\n- clip:\n- trim:\n- captions:\n",
    },
}


def open_surface(surface_id: str, args: dict[str, Any] | None, context: dict[str, Any] | None) -> dict[str, Any]:
    config = SURFACES[surface_id]
    payload = dict(args or {})
    conversation_id = str(payload.get("conversation_id") or (context or {}).get("conversation_id") or "").strip()
    resource_id = str(payload.get("resource_id") or f"{surface_id}:{conversation_id or 'scratch'}").strip()
    descriptor = {
        "id": resource_id,
        "kind": config["kind"],
        "title": config["title"],
        "sourcePackId": PACK_ID,
        "renderer": config["renderer"],
        "conversationId": conversation_id,
        "resourceId": resource_id,
        "payload": {
            "initial_text": str(payload.get("text") or payload.get("prompt") or config["initial_text"]),
            "selection": payload.get("selection"),
            "attached_files": payload.get("attached_files") if isinstance(payload.get("attached_files"), list) else [],
        },
        "layoutMode": "split",
        "chatPlacement": "left",
    }
    return {
        "status": "ok",
        "data": {
            "surface": descriptor,
            "effects": [{"type": "surface.open", "surface": descriptor}],
            "message": f"{config['title']} surface opened.",
        },
    }
