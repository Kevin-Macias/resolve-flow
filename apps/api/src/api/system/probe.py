"""Container probe with bounded waits and no raw connection errors in output."""

import os
from urllib.error import URLError
from urllib.request import urlopen


def main() -> None:
    try:
        port = int(os.getenv("PORT", "8000"))
        with urlopen(f"http://127.0.0.1:{port}/ready", timeout=4) as response:
            if response.status != 200:
                raise SystemExit(1)
    except (URLError, OSError, ValueError):
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
