"""
config/insecure_ssl.py
──────────────────────
Opt-in TLS verification bypass for corporate MITM proxies.

⚠️  INSECURE — this disables certificate verification for ALL outbound HTTPS.
    Only use on a trusted corporate network where a proxy re-signs traffic and
    you cannot install the corporate root CA. The proper fix is to build a CA
    bundle (see CURL_CA_BUNDLE / REQUESTS_CA_BUNDLE / SSL_CERT_FILE).

Activated by setting INSECURE_SSL=1 in the environment (.env). No-op otherwise.

Covers the three HTTP stacks the platform uses:
  • httpx     — OpenAI / Anthropic / Gemini SDKs (LLM calls, incl. Groq)
  • requests  — NewsAPI, misc REST fallbacks
  • curl_cffi — yfinance market-data fallback
  • stdlib ssl default context — urllib and anything else
"""

from __future__ import annotations

import os


def maybe_disable_tls_verification() -> bool:
    """If INSECURE_SSL=1, monkeypatch every HTTP client to skip cert checks.

    Returns True if verification was disabled, False if left intact.
    """
    if os.environ.get("INSECURE_SSL") != "1":
        return False

    # ── stdlib ssl (urllib, http.client, etc.) ───────────────
    try:
        import ssl

        ssl._create_default_https_context = ssl._create_unverified_context
    except Exception:
        pass

    # ── urllib3 warning noise ────────────────────────────────
    try:
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    except Exception:
        pass

    # ── requests: force verify=False on every request ────────
    try:
        import requests

        _orig_request = requests.Session.request

        def _request(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            kwargs["verify"] = False
            return _orig_request(self, *args, **kwargs)

        requests.Session.request = _request  # type: ignore[assignment]
    except Exception:
        pass

    # ── httpx: force verify=False on Client / AsyncClient ────
    #    The OpenAI + Anthropic SDKs build httpx clients internally.
    try:
        import httpx

        _orig_client_init = httpx.Client.__init__
        _orig_async_init = httpx.AsyncClient.__init__

        def _client_init(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            kwargs["verify"] = False
            return _orig_client_init(self, *args, **kwargs)

        def _async_init(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            kwargs["verify"] = False
            return _orig_async_init(self, *args, **kwargs)

        httpx.Client.__init__ = _client_init  # type: ignore[assignment]
        httpx.AsyncClient.__init__ = _async_init  # type: ignore[assignment]
    except Exception:
        pass

    # ── curl_cffi (yfinance): force verify=False on Session ──
    try:
        from curl_cffi import requests as _curl_requests

        _orig_curl_init = _curl_requests.Session.__init__

        def _curl_init(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            kwargs["verify"] = False
            return _orig_curl_init(self, *args, **kwargs)

        _curl_requests.Session.__init__ = _curl_init  # type: ignore[assignment]
    except Exception:
        pass

    return True
