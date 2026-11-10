"""Limit how large a request body one route accepts."""

from fastapi import FastAPI
from starlette.middleware.body_limit import RequestBodyLimitMiddleware


def limit_latest_route_body(app: FastAPI, max_bytes: int) -> None:
    """Refuse oversized bodies for the route registered just before this call.

    FastAPI saves an upload to temp storage before the route's own code runs, so a
    size check inside the route is too late to protect the disk. This stops the
    request as the bytes arrive. Limiting a route rather than the whole app lets
    each upload have its own limit. FastAPI's APIRoute does not expose Starlette's
    max_body_size argument, so this does what that argument does.
    """
    route = app.router.routes[-1]
    route.app = RequestBodyLimitMiddleware(route.app, max_body_size=max_bytes)
