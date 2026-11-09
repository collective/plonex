from importlib.util import module_from_spec
from importlib.util import spec_from_file_location
from pathlib import Path
from types import ModuleType
from types import SimpleNamespace
from unittest import mock
from xml.etree import ElementTree

import pytest
import sys


@pytest.fixture
def panel_module(monkeypatch):
    products = ModuleType("Products")
    products.__path__ = []
    five = ModuleType("Products.Five")
    five.__path__ = []
    browser = ModuleType("Products.Five.browser")

    class BrowserView:
        def __init__(self, context, request):
            self.context, self.request = context, request

    browser.BrowserView = BrowserView
    plone = ModuleType("plone")
    plone.__path__ = []
    protect = ModuleType("plone.protect")
    protect.CheckAuthenticator = mock.Mock()
    protect.PostOnly = mock.Mock()
    protect.createToken = mock.Mock(return_value="token")
    for module in (products, five, browser, plone, protect):
        monkeypatch.setitem(sys.modules, module.__name__, module)
    path = Path(__file__).parents[1] / "src/plonex/services/cron/browser.py"
    spec = spec_from_file_location("test_queue_view", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, protect


class Request(dict):
    def __init__(self, method="GET", form=None):
        super().__init__(REQUEST_METHOD=method)
        self.form = form or {}
        self.response = mock.Mock()


def test_panel_escapes_output_and_get_never_mutates(
    panel_module, monkeypatch, tmp_path
):
    module, protect = panel_module
    monkeypatch.setenv("PLONEX_PROJECT_ROOT", str(tmp_path))
    service = mock.Mock()
    service.jobs.jobs = [SimpleNamespace(name="safe", schedule="* * * * *")]
    service.invoke_runtime.return_value = {
        "worker": {"running": True},
        "queue": {
            "pending_count": 1,
            "scheduled_count": 0,
            "pending": [{"job": "<script>", "task_id": "task", "revoked": False}],
            "scheduled": [],
        },
        "recent_runs": [],
    }
    with mock.patch.object(module, "CronService", return_value=service):
        request = Request(form={"action": "enqueue", "value": "safe"})
        result = module.QueuePanel(
            SimpleNamespace(absolute_url=lambda: "http://example/Plone"), request
        )()
    assert "&lt;script&gt;" in result and "<script>" not in result
    assert 'name="_authenticator" value="token"' in result
    assert service.invoke_runtime.call_args_list == [mock.call("status")]
    protect.CheckAuthenticator.assert_not_called()
    request.response.setHeader.assert_any_call("Cache-Control", "no-store")


def test_panel_rejects_missing_csrf_before_calling_queue(
    panel_module, monkeypatch, tmp_path
):
    module, protect = panel_module
    monkeypatch.setenv("PLONEX_PROJECT_ROOT", str(tmp_path))
    protect.CheckAuthenticator.side_effect = PermissionError("invalid token")
    service = mock.Mock()
    request = Request("POST", {"action": "enqueue", "value": "safe"})
    with mock.patch.object(module, "CronService", return_value=service):
        with pytest.raises(PermissionError):
            module.QueuePanel(
                SimpleNamespace(absolute_url=lambda: "http://example/Plone"), request
            )()
    protect.PostOnly.assert_called_once_with(request)
    service.invoke_runtime.assert_not_called()


def test_panel_performs_only_allowlisted_authenticated_actions(
    panel_module, monkeypatch, tmp_path
):
    module, protect = panel_module
    monkeypatch.setenv("PLONEX_PROJECT_ROOT", str(tmp_path))
    service = mock.Mock()
    context = SimpleNamespace(absolute_url=lambda: "http://example/Plone")
    request = Request("POST", {"action": "enqueue", "value": "safe"})
    with mock.patch.object(module, "CronService", return_value=service):
        assert module.QueuePanel(context, request)() == ""
    protect.CheckAuthenticator.assert_called_once_with(request)
    service.jobs.get.assert_called_once_with("safe")
    service.invoke_runtime.assert_called_once_with("enqueue", "safe")
    request.response.redirect.assert_called_once_with(
        "http://example/Plone/@@plonex-queue"
    )
    service.reset_mock()
    request = Request("POST", {"action": "run-anything", "value": "safe"})
    with mock.patch.object(module, "CronService", return_value=service):
        with pytest.raises(ValueError, match="Invalid queue action"):
            module.QueuePanel(context, request)()
    service.invoke_runtime.assert_not_called()


def test_zcml_restricts_view_to_manage_portal():
    root = ElementTree.parse(
        Path(__file__).parents[1] / "src/plonex/services/cron/configure.zcml"
    ).getroot()
    pages = [element for element in root if element.tag.endswith("page")]
    assert len(pages) == 1
    assert pages[0].attrib["permission"] == "cmf.ManagePortal"
