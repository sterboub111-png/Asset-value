"""Route table, the `route` decorator and the per-request context."""
from __future__ import annotations

import re

Route = tuple[str, "re.Pattern[str]", callable]

ROUTES: list[Route] = []

def route(method: str, pattern: str):
    def deco(fn):
        ROUTES.append((method, re.compile("^" + pattern + "$"), fn))
        return fn
    return deco

class Ctx:
    def __init__(self, con, query, body, raw, headers, user=None, token=None):
        self.con, self.query, self.body, self.raw, self.headers = con, query, body, raw, headers
        self.user, self.token = user, token      # signed-in user (dict) and the session token
        self.cookies: list[str] = []             # Set-Cookie headers to send with the response

    def q(self, k, default=""):
        return self.query.get(k, [default])[0]
