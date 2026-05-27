from __future__ import annotations

import os

import uvicorn

from app.api.main import app
from app.core.local_security import should_enforce_loopback_host
from app.core.url_validation import is_loopback_host

def main() -> None:
    host = os.getenv("AVERA_DESK_HOST", "127.0.0.1")
    port = int(os.getenv("AVERA_DESK_PORT", "8000"))

    if should_enforce_loopback_host() and not is_loopback_host(host):
        raise RuntimeError(
            "Refusing to bind backend to a non-loopback host in packaged/production profile. "
            "Set AVERA_DESK_HOST to a loopback address."
        )

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=False,
    )


if __name__ == "__main__":
    main()
