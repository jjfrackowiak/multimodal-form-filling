"""The one function in the repo that constructs a real model client.

Auth is ADC and is deliberately invisible here: no `api_key=` argument, and none may be
added — see the B8 brief and `.env.example`. `google-genai`'s `Client` resolves credentials
itself (`GOOGLE_APPLICATION_CREDENTIALS`, then the gcloud ADC file, then the metadata
server) the first time `Gemini.api_client` is actually touched, which is lazy
(`cached_property`) and only happens on the first real model call — constructing a
`Gemini(...)` instance touches no network and needs no credential to succeed.
"""

from __future__ import annotations

from google.adk.models import Gemini
from google.genai import types

from editor_service.settings import Settings

__all__ = ["build_editor_model"]


def build_editor_model(settings: Settings) -> Gemini:
    """The editor's model: `EDITOR_MODEL_ID`, pinned, ADC-authenticated, retried.

    `GOOGLE_CLOUD_PROJECT`/`GOOGLE_CLOUD_LOCATION`/`GOOGLE_GENAI_USE_ENTERPRISE` are read
    by `google-genai` from the process environment when the client is eventually built —
    this function does not pass them through explicitly, on purpose: that is what "nothing
    in our code branches on which credential source won" means in practice. `Settings`
    exists so a missing project id fails loudly before this is ever called, not so this
    function can thread it through by hand.
    """
    return Gemini(
        model=settings.editor_model_id,
        retry_options=types.HttpRetryOptions(attempts=3),
    )
