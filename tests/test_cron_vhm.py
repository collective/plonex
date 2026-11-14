import pytest


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (
            "/VirtualHostBase/https/example.com:443/Plone/client/",
            "https://example.com/Plone/client",
        ),
        (
            "/VirtualHostBase/https/example.com:443/Plone/client/VirtualHostRoot/",
            "https://example.com",
        ),
    ],
)
def test_virtual_host_path_sets_real_zope_urls(path, expected):
    pytest.importorskip("Testing.ZopeTestCase.ZopeLite")
    from Testing.makerequest import makerequest
    from Testing.ZopeTestCase.ZopeLite import app as zope_app

    import transaction

    transaction.begin()
    app = makerequest(zope_app())
    try:
        app.manage_addFolder("Plone")
        app.Plone.manage_addFolder("client")
        app.REQUEST.set("PARENTS", [app])
        app.REQUEST.traverse(path)
        assert app.Plone.client.absolute_url() == expected
    finally:
        transaction.abort()
        app._p_jar.close()
