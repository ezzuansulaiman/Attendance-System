"""Unified entrypoint for local runs and Railway services."""

import os
import subprocess
import sys
import time


def _run_all():
    env_base = os.environ.copy()
    script_path = os.path.abspath(__file__)

    services = []
    for service_mode in ("web", "bot"):
        env = env_base.copy()
        env["SERVICE_MODE"] = service_mode
        proc = subprocess.Popen([sys.executable, script_path], env=env)
        services.append((service_mode, proc))

    print("Attendance System running in combined mode: web + bot")

    try:
        while True:
            for service_mode, proc in services:
                code = proc.poll()
                if code is not None:
                    raise SystemExit(
                        f"Service '{service_mode}' berhenti dengan kod keluar {code}."
                    )
            time.sleep(1)
    except KeyboardInterrupt:
        print("Menghentikan web dan bot...")
    finally:
        for _, proc in services:
            if proc.poll() is None:
                proc.terminate()
        for _, proc in services:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


def main():
    service_mode = os.getenv("SERVICE_MODE", "web").strip().lower()

    if service_mode == "all":
        _run_all()
        return

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
