"""Standalone zconsole script; imports Plone from the project's interpreter.

Keep the job's domain function separate from any browser view. This is trusted
server-side work, executed as an explicitly configured existing Plone user.
"""

import importlib
import json
import os


def execute(app, specification):
    from plone.api.env import adopt_user  # type: ignore[import-not-found]
    from zope.component.hooks import getSite  # type: ignore[import-not-found]
    from zope.component.hooks import setSite  # type: ignore[import-not-found]

    import transaction  # type: ignore[import-not-found]

    old_site = getSite()
    try:
        site = app.unrestrictedTraverse(specification["site"].strip("/"))
        setSite(site)
        with adopt_user(username=specification["user"]):
            context = site.restrictedTraverse(
                specification.get("context", "").strip("/")
            )
            module, function = specification["callable"].split(":", 1)
            callback = importlib.import_module(module)
            for part in function.split("."):
                callback = getattr(callback, part)
            transaction.begin()
            result = callback(context, **specification.get("kwargs", {}))
            transaction.commit()
            return result
    except BaseException:
        transaction.abort()
        raise
    finally:
        setSite(old_site)


if __name__ == "__main__":
    with open(os.environ["PLONEX_JOB_SPEC"], encoding="utf-8") as handle:
        result = execute(globals()["app"], json.load(handle))
    if result is not None:
        print(json.dumps(result, default=str))
