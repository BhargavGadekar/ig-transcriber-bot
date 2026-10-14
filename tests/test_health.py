import asyncio
import json
import urllib.request
from core.health import start_health_server

def test_health_server():
    async def run():
        port = 18088
        stats = {"uptime_s": 10.5, "workers": 1, "jobs_done": 2}
        server = await start_health_server(port, lambda: stats)

        loop = asyncio.get_running_loop()

        def fetch(path):
            req = urllib.request.Request(f"http://127.0.0.1:{port}{path}")
            try:
                with urllib.request.urlopen(req, timeout=2.0) as resp:
                    return resp.status, resp.read().decode("utf-8")
            except urllib.error.HTTPError as exc:
                return exc.code, exc.read().decode("utf-8")

        # GET /health
        status, body = await loop.run_in_executor(None, fetch, "/health")
        assert status == 200
        data = json.loads(body)
        assert data["uptime_s"] == 10.5
        assert data["jobs_done"] == 2

        # GET /other
        status404, body404 = await loop.run_in_executor(None, fetch, "/other")
        assert status404 == 404
        assert "not found" in body404

        server.close()
        await server.wait_closed()

    asyncio.run(run())
