"""`python -m app` — run the API with a readable error on bad configuration."""

import sys

import uvicorn
from smoke_shared.config import ConfigError, load_settings


def main() -> int:
    try:
        s = load_settings()
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 2
    uvicorn.run(
        "app.main:get_app", factory=True, host=s.api_host, port=s.api_port, log_config=None, access_log=False
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
