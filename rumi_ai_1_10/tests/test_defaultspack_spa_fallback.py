from __future__ import annotations

from ecosystem.defaultspack.transport.http import DefaultsHttpServer


def test_direct_desktops_route_serves_shell_after_route_miss() -> None:
    server = DefaultsHttpServer(None)

    handler, path_params, source, path_inject, pattern = server._match_route("GET", "/desktops")

    assert handler == server._handle_static
    assert path_params == {}
    assert source == "fallback"
    assert path_inject == {}
    assert pattern == ""


def test_direct_desktops_route_allows_trailing_slash() -> None:
    server = DefaultsHttpServer(None)

    handler, path_params, source, path_inject, pattern = server._match_route("GET", "/desktops/")

    assert handler == server._handle_static
    assert path_params == {}
    assert source == "fallback"
    assert path_inject == {}
    assert pattern == ""


def test_api_desktops_remains_api_route() -> None:
    server = DefaultsHttpServer(None)

    handler, _path_params, source, _path_inject, pattern = server._match_route(
        "GET",
        "/api/desktops",
    )

    assert handler is not None
    assert handler != server._handle_static
    assert source in {"fallback", "registry"}
    assert pattern == "/api/desktops"


def test_unknown_api_route_does_not_use_spa_fallback() -> None:
    server = DefaultsHttpServer(None)

    handler, path_params, source, path_inject, pattern = server._match_route(
        "GET",
        "/api/not-a-real-route",
    )

    assert handler is None
    assert path_params is None
    assert source is None
    assert path_inject is None
    assert pattern is None


def test_unknown_web_route_does_not_use_spa_fallback() -> None:
    server = DefaultsHttpServer(None)

    handler, path_params, source, path_inject, pattern = server._match_route(
        "GET",
        "/not-a-real-route",
    )

    assert handler is None
    assert path_params is None
    assert source is None
    assert path_inject is None
    assert pattern is None


def test_spa_fallback_ignores_post_and_asset_like_paths() -> None:
    server = DefaultsHttpServer(None)

    post_handler, *_post_rest = server._match_route("POST", "/desktops")
    asset_handler, *_asset_rest = server._match_route("GET", "/desktops.json")

    assert post_handler is None
    assert asset_handler is None
