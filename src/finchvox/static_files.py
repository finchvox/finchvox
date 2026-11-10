"""Serve the UI so browsers always pick up a new version.

Without a Cache-Control header, browsers guess how long to reuse a file, so
after an upgrade a page could run with the previous version's CSS or
JavaScript. "no-cache" still lets the browser keep its copy, but it checks
with the server first, which answers 304 Not Modified when nothing changed.
"""

from pathlib import Path

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

REVALIDATE = "no-cache"


class RevalidatedStaticFiles(StaticFiles):
    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = REVALIDATE
        return response


def page_response(path: Path) -> FileResponse:
    return FileResponse(str(path), headers={"Cache-Control": REVALIDATE})
