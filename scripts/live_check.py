"""Query a real router with the integration's client, without Home Assistant.

Usage: DDWRT_HOST=192.168.1.1 DDWRT_USER=admin DDWRT_PASSWORD=... python scripts/live_check.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "custom_components", "ddwrt_monitor"))
import api  # noqa: E402


async def main() -> None:
    client = api.DdwrtClient(os.environ["DDWRT_HOST"], os.environ.get("DDWRT_USER", "admin"), os.environ["DDWRT_PASSWORD"])
    data = await client.fetch()
    for key in ("router", "vpn", "networks", "clients", "public", "traffic"):
        print(f"{key}: {getattr(data, key)}")


asyncio.run(main())
