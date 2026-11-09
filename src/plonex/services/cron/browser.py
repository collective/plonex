"""Optional Plone management view, loaded only in a configured target runtime."""

from html import escape
from pathlib import Path
from plonex.files import read_only
from plonex.inspection import safe_value
from plonex.services.cron import CronService
from Products.Five.browser import BrowserView  # type: ignore[import-not-found]

import os


def escaped(value):
    return escape(str(value), quote=True)


class QueuePanel(BrowserView):
    """Permission is enforced by ZCML; every mutation requires POST and CSRF."""

    def __call__(self):
        from plone.protect import CheckAuthenticator  # type: ignore[import-not-found]
        from plone.protect import createToken  # type: ignore[import-not-found]
        from plone.protect import PostOnly  # type: ignore[import-not-found]

        root = os.environ.get("PLONEX_PROJECT_ROOT")
        if not root or not Path(root).is_absolute():
            raise ValueError("Plonex project root is not configured for this instance")
        with read_only():
            service = CronService(target=Path(root))
            service.options
        message = ""
        if self.request.get("REQUEST_METHOD", "GET").upper() == "POST":
            PostOnly(self.request)
            CheckAuthenticator(self.request)
            action = self.request.form.get("action", "")
            value = self.request.form.get("value", "")
            if (
                not isinstance(value, str)
                or not value
                or action not in {"enqueue", "retry", "revoke", "restore"}
            ):
                raise ValueError("Invalid queue action")
            if action == "enqueue":
                service.jobs.get(value)
            service.invoke_runtime(action, value)
            self.request.response.redirect(
                self.context.absolute_url() + "/@@plonex-queue"
            )
            return ""
        try:
            state = service.invoke_runtime("status")
            jobs = service.jobs.jobs
        except (ValueError, OSError) as error:
            state, jobs = None, ()
            message = safe_value(str(error))
        token = escaped(createToken())
        endpoint = escaped(self.context.absolute_url() + "/@@plonex-queue")

        def form(action, value, label):
            return (
                f'<form method="post" action="{endpoint}">'
                f'<input type="hidden" name="_authenticator" value="{token}">'
                f'<input type="hidden" name="action" value="{escaped(action)}">'
                f'<input type="hidden" name="value" value="{escaped(value)}">'
                f'<button type="submit">{escaped(label)}</button></form>'
            )

        html = [
            '<!doctype html><html><head><meta charset="utf-8">'
            "<title>Plonex queue</title></head><body><main>"
            "<h1>Plonex queue</h1>"
        ]
        if message:
            html.append(f"<p>{escaped(message)}</p>")
        if state:
            queue = state["queue"]
            worker = "running" if state["worker"]["running"] else "stopped"
            html.append(
                f'<p>Worker: {worker}; pending: {queue["pending_count"]}; '
                f'scheduled: {queue["scheduled_count"]}</p>'
            )
            html.append("<h2>Jobs</h2><ul>")
            for job in jobs:
                html.append(
                    f"<li>{escaped(job.name)} — {escaped(job.schedule)} "
                    f'{form("enqueue", job.name, "Queue")}</li>'
                )
            html.append("</ul><h2>Queued tasks</h2><ul>")
            for group in ("pending", "scheduled"):
                for task in queue[group]:
                    action = "restore" if task["revoked"] else "revoke"
                    control = form(action, task["task_id"], action.title())
                    html.append(
                        f'<li>{escaped(task["job"])}: {escaped(task["task_id"])} '
                        f"({escaped(group)}) {control}</li>"
                    )
            html.append("</ul><h2>Recent attempts</h2><ul>")
            for run in state["recent_runs"]:
                action = ""
                if run.get("task_id") and run["status"] in {
                    "failed",
                    "timed-out",
                    "interrupted",
                }:
                    action = form("retry", run["task_id"], "Retry")
                html.append(
                    f'<li>{escaped(run["job"])}: {escaped(run["status"])} '
                    f'{escaped(run.get("task_id") or "")} {action}</li>'
                )
            html.append("</ul>")
        html.append("</main></body></html>")
        self.request.response.setHeader("Content-Type", "text/html; charset=utf-8")
        self.request.response.setHeader("Cache-Control", "no-store")
        return "".join(html)
