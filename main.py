"""Unified entrypoint for local runs and Railway services."""

import os


def main():
    service_mode = os.getenv("SERVICE_MODE", "web").strip().lower()
    if service_mode == "bot":
        import bot

        bot.main()
        return

    if service_mode == "web":
        import app

        app.run_server()
        return

    raise SystemExit(f"SERVICE_MODE tidak sah: {service_mode}")


if __name__ == "__main__":
    main()
