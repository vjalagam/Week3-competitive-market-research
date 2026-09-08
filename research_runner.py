"""Run provider work in a killable process with a wall-clock deadline."""
from __future__ import annotations

import json
import os
from pathlib import Path
import select
import subprocess
import sys
import time


class ResearchRunError(RuntimeError):
    pass


def run_research(company, search_key, model_key, model="openrouter/free",
                 app_url="", endpoint=None, *, timeout=120, on_progress=None, max_competitors=3):
    if type(max_competitors) is not int or not 1 <= max_competitors <= 3:
        raise ValueError("Choose between one and three competitors")
    if not company.strip():
        raise ValueError("Enter a company name first.")
    config = dict(company=company, search_key=search_key, model_key=model_key,
                  model=model, app_url=app_url, endpoint=endpoint, max_competitors=max_competitors)
    return _run_worker(config, timeout, on_progress)


def _run_worker(config, timeout, on_progress=None, command=None):
    if timeout <= 0:
        raise ValueError("Research timeout must be positive")
    reports = []
    def incomplete(message):
        if not reports:
            raise ResearchRunError(message)
        return {"company": config["company"].strip(), "reports": reports,
                "partial": True, "status": message,
                "requested_competitors": config.get("max_competitors", 3)}

    started = time.monotonic()
    process = subprocess.Popen(
        command or [sys.executable, str(Path(__file__).resolve()), "--worker"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    try:
        process.stdin.write(json.dumps(config).encode())
        process.stdin.close()
        buffer = b""
        while True:
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                return incomplete(
                    f"Research stopped after {timeout:g} seconds. The provider took too long. "
                    + ("Try researching one competitor at a time."
                     if config.get("max_competitors", 3) > 1 else
                     "The provider could not finish one competitor in time. Retry later.")
                )
            ready, _, _ = select.select([process.stdout], [], [], min(remaining, 0.2))
            if not ready:
                continue
            chunk = os.read(process.stdout.fileno(), 65536)
            if not chunk:
                return incomplete("The research worker stopped without a result.")
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                event = json.loads(line)
                if event["type"] == "progress" and on_progress:
                    on_progress(event["message"])
                elif event["type"] == "error":
                    return incomplete(event["message"])
                elif event["type"] == "report":
                    from models import CompetitorReport
                    reports.append(CompetitorReport.model_validate(event["report"]))
                elif event["type"] == "result":
                    from models import CompetitorReport
                    result = event["result"]
                    result["reports"] = [CompetitorReport.model_validate(r) for r in result["reports"]]
                    return result
    finally:
        # Always stop work, including when the UI reruns or the callback raises.
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)
        process.stdout.close()
        if not process.stdin.closed:
            process.stdin.close()


def _worker():
    from analyst import CompetitorAnalyst, ModelOutputError
    from pipeline import CompetitiveResearchPipeline
    from youcom_client import YouComClient

    def emit(event):
        print(json.dumps(event), flush=True)

    try:
        config = json.load(sys.stdin)
        pipeline = CompetitiveResearchPipeline(
            YouComClient(config["search_key"], endpoint=config["endpoint"]),
            CompetitorAnalyst(config["model_key"], config["model"], config["app_url"]),
            progress=lambda message: emit({"type": "progress", "message": message}),
            on_report=lambda report: emit({"type": "report", "report": report.model_dump()}),
            max_competitors=config.get("max_competitors", 3),
        )
        result = pipeline.run(config["company"])
        result["reports"] = [r.model_dump() for r in result["reports"]]
        result["search_results"] = {}
        result["partial"] = False
        result["requested_competitors"] = config.get("max_competitors", 3)
        emit({"type": "result", "result": result})
    except Exception as exc:
        if isinstance(exc, ModelOutputError):
            message = str(exc)
        else:
            code = getattr(exc, "status_code", None)
            response = getattr(exc, "response", None)
            if response is not None:
                code = response.status_code
            message = f"Provider request failed ({type(exc).__name__}"
            message += f", HTTP {code})." if code else ")."
            advice = {
                401: " Check the provider API key.",
                402: " The provider requires available credits.",
                403: " Check the account's API access.",
                404: " The selected model or endpoint is unavailable. Choose another model.",
                429: " The provider is rate-limiting requests. Retry later or choose another model.",
            }
            message += advice.get(code, " Check provider availability, then retry.")
        emit({"type": "error", "message": message})


if __name__ == "__main__":
    _worker()
