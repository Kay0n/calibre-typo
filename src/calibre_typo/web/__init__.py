from __future__ import annotations

from flask import Flask, jsonify, render_template, request

from ..epub import normalize
from ..library import LibraryUnavailable
from . import api, auth, devices, review
from .filters import fixes, match_label, short_time, word_diff
from .security import check_csrf, csrf_token, is_logged_in, login_enabled


def register(app: Flask) -> None:
    for blueprint in (auth.bp, review.bp, devices.bp, api.bp):
        app.register_blueprint(blueprint)

    app.before_request(check_csrf)
    app.jinja_env.globals.update(csrf_token=csrf_token, is_logged_in=is_logged_in, login_enabled=login_enabled)
    app.jinja_env.filters.update(word_diff=word_diff, short_time=short_time, normalize=normalize,
                                 fixes=fixes, match_label=match_label)

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("Content-Security-Policy",
                                    "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        return response

    @app.errorhandler(LibraryUnavailable)
    def library_unavailable(err):
        if request.blueprint == "api":
            return jsonify(error=str(err)), 503
        return render_template("error.html", title="Library unavailable", message=str(err)), 503

    @app.get("/healthz")
    def healthz():
        return jsonify(ok=True)
