from core_runtime.port_standards import can_connect_ports, normalize_port_standards


def test_normalize_port_standards_supports_legacy_contract_fields() -> None:
    assert normalize_port_standards({"contract": "rumi.tool.bundle"}) == ["rumi.tool.bundle"]
    assert normalize_port_standards({"contracts": ["rumi.tool.bundle"]}) == ["rumi.tool.bundle"]
    assert normalize_port_standards({"standards": ["rumi.tool.bundle"]}) == ["rumi.tool.bundle"]


def test_can_connect_ports_accepts_mixed_legacy_and_standard_shapes() -> None:
    assert can_connect_ports(
        "output",
        {"contract": "rumi.tool.bundle"},
        "input",
        {"standards": ["rumi.tool.bundle"]},
    )


def test_can_connect_ports_rejects_mismatch_direction_and_empty_standards() -> None:
    assert not can_connect_ports(
        "input",
        {"standards": ["rumi.tool.bundle"]},
        "input",
        {"standards": ["rumi.tool.bundle"]},
    )
    assert not can_connect_ports("output", {"standards": []}, "input", {"contracts": []})
    assert not can_connect_ports(
        "output",
        {"standards": ["rumi.tool.bundle"]},
        "input",
        {"standards": ["rumi.prompt.bundle"]},
    )
