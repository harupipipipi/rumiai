from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK))


def test_mobile_tool_records_tag_compatible_tools() -> None:
    from domain.mobile.tools import MOBILE_COMPATIBLE_TAG, mobile_tool_records

    records = mobile_tool_records(
        [
            {
                "tool_id": "web_search",
                "name": "web_search",
                "summary": "Search the web",
                "tags": ["web"],
            }
        ]
    )

    assert records[0]["mobile_compatible"] is True
    assert MOBILE_COMPATIBLE_TAG in records[0]["tags"]
    assert records[0]["mobile"]["execution_location"] == "pc"
    assert records[0]["mobile"]["platforms"] == ["ios", "android"]
    assert "pc-defaultspack-runtime" in records[0]["mobile"]["runtime_layers"]
    assert records[0]["callable"] is True
    assert records[0]["execution_route"] == "pc"
    assert records[0]["automatic_routing"]["one_tool_surface"] is True


def test_mobile_tool_records_explain_host_bound_tools() -> None:
    from domain.mobile.tools import MOBILE_COMPATIBLE_TAG, mobile_tool_records

    records = mobile_tool_records(
        [
            {
                "tool_id": "desktop_input",
                "name": "desktop_input",
                "summary": "Control desktop input",
                "tags": ["desktop", "computer_use"],
            }
        ]
    )

    assert records[0]["mobile_compatible"] is False
    assert MOBILE_COMPATIBLE_TAG not in records[0]["tags"]
    assert "スマホ単体では" in records[0]["mobile_unavailable_reason"]
    assert records[0]["mobile"]["implementation_status"] == "pc_only"
    assert records[0]["mobile"]["platforms"] == []
    assert records[0]["callable"] is False
    assert records[0]["execution_route"] == "unavailable"


def test_mobile_tool_records_mark_phone_local_overrides() -> None:
    from domain.mobile.tools import mobile_tool_records

    records = mobile_tool_records(
        [
            {
                "tool_id": "browser_open_url",
                "name": "browser_open_url",
                "summary": "Open a URL",
                "service_id": "browser",
                "tags": ["browser", "tool"],
            },
            {
                "tool_id": "media_clipboard_read",
                "name": "media_clipboard_read",
                "summary": "Read clipboard",
                "tags": ["media", "tool"],
            },
            {
                "tool_id": "media_file_pick",
                "name": "media_file_pick",
                "summary": "Pick a phone file",
                "tags": ["media", "tool"],
            },
            {
                "tool_id": "media_screenshot",
                "name": "media_screenshot",
                "summary": "Capture a phone screenshot",
                "tags": ["media", "tool"],
            },
            {
                "tool_id": "media_image_read",
                "name": "media_image_read",
                "summary": "Read image metadata",
                "tags": ["media", "tool"],
            },
            {
                "tool_id": "media_image_transform",
                "name": "media_image_transform",
                "summary": "Transform image bytes",
                "tags": ["media", "tool"],
            },
            {
                "tool_id": "image_resize",
                "name": "image_resize",
                "summary": "Resize image bytes",
                "tags": ["media", "agent_os", "artifact_workspace"],
            },
            {
                "tool_id": "image_convert",
                "name": "image_convert",
                "summary": "Convert image bytes",
                "tags": ["media", "agent_os", "artifact_workspace"],
            },
            {
                "tool_id": "media_ocr",
                "name": "media_ocr",
                "summary": "Run OCR",
                "tags": ["media", "tool"],
            },
            {
                "tool_id": "ocr_extract",
                "name": "ocr_extract",
                "summary": "Extract OCR text",
                "tags": ["media", "agent_os", "artifact_workspace"],
            },
            {
                "tool_id": "media_doc_parse",
                "name": "media_doc_parse",
                "summary": "Parse a text document",
                "tags": ["media", "tool"],
            },
            {
                "tool_id": "media_pdf_parse",
                "name": "media_pdf_parse",
                "summary": "Parse PDF bytes",
                "tags": ["media", "tool"],
            },
            {
                "tool_id": "pdf_extract",
                "name": "pdf_extract",
                "summary": "Extract PDF bytes",
                "tags": ["media", "agent_os", "artifact_workspace"],
            },
            {
                "tool_id": "pdf_extract_tables",
                "name": "pdf_extract_tables",
                "summary": "Extract PDF tables",
                "tags": ["media", "agent_os", "artifact_workspace"],
            },
            {
                "tool_id": "source_extract",
                "name": "source_extract",
                "summary": "Extract source payload",
                "tags": ["research", "agent_os", "artifact_workspace"],
            },
            {
                "tool_id": "source_rank",
                "name": "source_rank",
                "summary": "Rank source snippets",
                "tags": ["research", "agent_os", "artifact_workspace"],
            },
            {
                "tool_id": "tts_generate",
                "name": "tts_generate",
                "summary": "Generate fallback audio",
                "tags": ["media", "agent_os", "artifact_workspace"],
            },
            {
                "tool_id": "tts_generate_local",
                "name": "tts_generate_local",
                "summary": "Generate fallback audio locally",
                "tags": ["media", "agent_os", "artifact_workspace"],
            },
        ]
    )

    by_id = {record["tool_id"]: record for record in records}
    assert by_id["browser_open_url"]["mobile_compatible"] is True
    assert by_id["browser_open_url"]["execution_route"] == "phone"
    assert by_id["browser_open_url"]["mobile"]["requires_pc"] is False
    assert "ios-swift" in by_id["browser_open_url"]["mobile"]["runtime_layers"]

    assert by_id["media_clipboard_read"]["mobile_compatible"] is True
    assert by_id["media_clipboard_read"]["execution_route"] == "phone"
    assert by_id["media_clipboard_read"]["mobile"]["requires_mobile_approval"] is True
    assert by_id["media_clipboard_read"]["mobile"]["implementation_status"] == "implemented"

    assert by_id["media_file_pick"]["mobile_compatible"] is True
    assert by_id["media_file_pick"]["execution_route"] == "phone"
    assert by_id["media_file_pick"]["mobile"]["requires_mobile_approval"] is True
    assert by_id["media_file_pick"]["mobile"]["implementation_status"] == "implemented"
    assert "ios-swift" in by_id["media_file_pick"]["mobile"]["runtime_layers"]
    assert "android-kotlin" in by_id["media_file_pick"]["mobile"]["runtime_layers"]

    assert by_id["media_screenshot"]["mobile_compatible"] is True
    assert by_id["media_screenshot"]["execution_route"] == "phone"
    assert by_id["media_screenshot"]["mobile"]["requires_mobile_approval"] is True
    assert by_id["media_screenshot"]["mobile"]["implementation_status"] == "implemented"
    assert "ios-swift" in by_id["media_screenshot"]["mobile"]["runtime_layers"]
    assert "android-kotlin" in by_id["media_screenshot"]["mobile"]["runtime_layers"]

    assert by_id["media_image_read"]["mobile_compatible"] is True
    assert by_id["media_image_read"]["execution_route"] == "phone"
    assert by_id["media_image_read"]["mobile"]["requires_mobile_approval"] is False
    assert by_id["media_image_read"]["mobile"]["implementation_status"] == "implemented"
    assert "flutter" in by_id["media_image_read"]["mobile"]["runtime_layers"]
    assert "dart" in by_id["media_image_read"]["mobile"]["runtime_layers"]

    assert by_id["media_image_transform"]["mobile_compatible"] is True
    assert by_id["media_image_transform"]["execution_route"] == "phone"
    assert by_id["media_image_transform"]["mobile"]["requires_mobile_approval"] is False
    assert by_id["media_image_transform"]["mobile"]["implementation_status"] == "implemented"
    assert "ios-swift" in by_id["media_image_transform"]["mobile"]["runtime_layers"]
    assert "android-kotlin" in by_id["media_image_transform"]["mobile"]["runtime_layers"]

    assert by_id["image_resize"]["mobile_compatible"] is True
    assert by_id["image_resize"]["execution_route"] == "phone"
    assert by_id["image_resize"]["mobile"]["requires_mobile_approval"] is False
    assert by_id["image_resize"]["mobile"]["implementation_status"] == "implemented_payload_only"
    assert "ios-swift" in by_id["image_resize"]["mobile"]["runtime_layers"]
    assert "android-kotlin" in by_id["image_resize"]["mobile"]["runtime_layers"]

    assert by_id["image_convert"]["mobile_compatible"] is True
    assert by_id["image_convert"]["execution_route"] == "phone"
    assert by_id["image_convert"]["mobile"]["requires_mobile_approval"] is False
    assert by_id["image_convert"]["mobile"]["implementation_status"] == "implemented_payload_only"
    assert "ios-swift" in by_id["image_convert"]["mobile"]["runtime_layers"]
    assert "android-kotlin" in by_id["image_convert"]["mobile"]["runtime_layers"]

    assert by_id["media_ocr"]["mobile_compatible"] is True
    assert by_id["media_ocr"]["execution_route"] == "phone"
    assert by_id["media_ocr"]["mobile"]["requires_mobile_approval"] is False
    assert by_id["media_ocr"]["mobile"]["implementation_status"] == "implemented_native_ocr_bridge"
    assert "ios-swift" in by_id["media_ocr"]["mobile"]["runtime_layers"]
    assert "android-kotlin" in by_id["media_ocr"]["mobile"]["runtime_layers"]

    assert by_id["ocr_extract"]["mobile_compatible"] is True
    assert by_id["ocr_extract"]["execution_route"] == "phone"
    assert by_id["ocr_extract"]["mobile"]["requires_mobile_approval"] is False
    assert by_id["ocr_extract"]["mobile"]["implementation_status"] == "implemented_payload_only_native_ocr"
    assert "ios-swift" in by_id["ocr_extract"]["mobile"]["runtime_layers"]
    assert "android-kotlin" in by_id["ocr_extract"]["mobile"]["runtime_layers"]

    assert by_id["media_doc_parse"]["mobile_compatible"] is True
    assert by_id["media_doc_parse"]["execution_route"] == "phone"
    assert by_id["media_doc_parse"]["mobile"]["requires_mobile_approval"] is False
    assert by_id["media_doc_parse"]["mobile"]["implementation_status"] == "implemented_text_documents"
    assert "flutter" in by_id["media_doc_parse"]["mobile"]["runtime_layers"]
    assert "dart" in by_id["media_doc_parse"]["mobile"]["runtime_layers"]

    assert by_id["media_pdf_parse"]["mobile_compatible"] is True
    assert by_id["media_pdf_parse"]["execution_route"] == "phone"
    assert by_id["media_pdf_parse"]["mobile"]["requires_mobile_approval"] is False
    assert by_id["media_pdf_parse"]["mobile"]["implementation_status"] == "implemented_best_effort_bytes"
    assert "flutter" in by_id["media_pdf_parse"]["mobile"]["runtime_layers"]
    assert "dart" in by_id["media_pdf_parse"]["mobile"]["runtime_layers"]

    assert by_id["pdf_extract"]["mobile_compatible"] is True
    assert by_id["pdf_extract"]["execution_route"] == "phone"
    assert by_id["pdf_extract"]["mobile"]["requires_mobile_approval"] is False
    assert by_id["pdf_extract"]["mobile"]["implementation_status"] == "implemented_best_effort_bytes"
    assert "flutter" in by_id["pdf_extract"]["mobile"]["runtime_layers"]
    assert "dart" in by_id["pdf_extract"]["mobile"]["runtime_layers"]

    assert by_id["pdf_extract_tables"]["mobile_compatible"] is True
    assert by_id["pdf_extract_tables"]["execution_route"] == "phone"
    assert by_id["pdf_extract_tables"]["mobile"]["requires_mobile_approval"] is False
    assert by_id["pdf_extract_tables"]["mobile"]["implementation_status"] == "implemented_empty_table_fallback"
    assert "flutter" in by_id["pdf_extract_tables"]["mobile"]["runtime_layers"]
    assert "dart" in by_id["pdf_extract_tables"]["mobile"]["runtime_layers"]

    assert by_id["source_extract"]["mobile_compatible"] is True
    assert by_id["source_extract"]["execution_route"] == "phone"
    assert by_id["source_extract"]["mobile"]["requires_mobile_approval"] is False
    assert by_id["source_extract"]["mobile"]["implementation_status"] == "implemented_payload_only"
    assert "flutter" in by_id["source_extract"]["mobile"]["runtime_layers"]
    assert "dart" in by_id["source_extract"]["mobile"]["runtime_layers"]

    assert by_id["source_rank"]["mobile_compatible"] is True
    assert by_id["source_rank"]["execution_route"] == "phone"
    assert by_id["source_rank"]["mobile"]["requires_mobile_approval"] is False
    assert by_id["source_rank"]["mobile"]["implementation_status"] == "implemented"
    assert "flutter" in by_id["source_rank"]["mobile"]["runtime_layers"]
    assert "dart" in by_id["source_rank"]["mobile"]["runtime_layers"]

    assert by_id["tts_generate"]["mobile_compatible"] is True
    assert by_id["tts_generate"]["execution_route"] == "phone"
    assert by_id["tts_generate"]["mobile"]["requires_mobile_approval"] is False
    assert by_id["tts_generate"]["mobile"]["implementation_status"] == "implemented_silent_wav_fallback"
    assert "flutter" in by_id["tts_generate"]["mobile"]["runtime_layers"]
    assert "dart" in by_id["tts_generate"]["mobile"]["runtime_layers"]

    assert by_id["tts_generate_local"]["mobile_compatible"] is True
    assert by_id["tts_generate_local"]["execution_route"] == "phone"
    assert by_id["tts_generate_local"]["mobile"]["requires_mobile_approval"] is False
    assert by_id["tts_generate_local"]["mobile"]["implementation_status"] == "implemented_silent_wav_fallback"
    assert "flutter" in by_id["tts_generate_local"]["mobile"]["runtime_layers"]
    assert "dart" in by_id["tts_generate_local"]["mobile"]["runtime_layers"]


def test_mobile_tool_summary_includes_defaultspack_agent_template() -> None:
    from domain.mobile.tools import mobile_tool_records, mobile_tool_summary

    records = mobile_tool_records([{"tool_id": "web_search", "name": "web_search"}])
    summary = mobile_tool_summary(records)

    assert summary["compatible_count"] == 1
    assert summary["agent_template"]["template_id"] == "rumi.composer.default"
    assert summary["agent_template"]["ai_input_id"] == "rumi.composer.default:default_ai_input"
    assert summary["platform_tags"]["ios"] == "mobile-ios"
    assert summary["tool_surface"]["mode"] == "unified"
    assert summary["tool_surface"]["one_tool_surface"] is True
