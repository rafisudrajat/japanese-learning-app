from server.resources import resource_path


def test_resource_path_resolves() -> None:
    web = resource_path("web")
    assert web.exists()
    assert (web / "index.html").exists()
