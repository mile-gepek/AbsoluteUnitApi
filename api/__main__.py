import uvicorn

from api.config import get_config
from api.log import get_log_config

config = get_config()


def main() -> int:
    uvicorn.run(
        "api.app:app",
        host="0.0.0.0",
        log_config=get_log_config(),
        reload=config.debug,
        reload_dirs=["api"],
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
