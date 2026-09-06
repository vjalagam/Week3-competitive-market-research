from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import re
from typing import Any

import requests

from models import SearchResult


class YouComClient:
    """Minimal You.com Search API adapter for fresh web and news research."""

    endpoint = "https://ydc-index.io/v1/search"

    def __init__(self, api_key: str, timeout: int = 12, endpoint: str | None = None) -> None:
        self.api_key = api_key
        self.timeout = timeout
        self.endpoint = endpoint or self.endpoint

    def search(self, query: str, *, freshness: str | None = None) -> list[SearchResult]:
        payload: dict[str, str] = {"query": query}
        if freshness:
            payload["freshness"] = freshness
        response = requests.post(
            self.endpoint,
            json=payload,
            headers={
                "X-API-Key": self.api_key,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=self.timeout,
        )
        if response.status_code == 401:
            raise requests.HTTPError(
                "You.com rejected YDC_API_KEY (401 Unauthorized). "
                "Create or copy a valid Search API key from the You.com platform.",
                response=response,
            )
        if response.status_code == 403:
            raise requests.HTTPError(
                "You.com denied access (403 Forbidden). "
                "Enable Search API access or use a key from an account with API credits.",
                response=response,
            )
        response.raise_for_status()
        return self._parse_results(response.json())

    def search_competitors(self, company: str) -> list[str]:
        results = self.search_competitor_evidence(company)
        names: list[str] = []
        for result in results:
            candidate = result.title.split(" - ")[0].split(" | ")[0].strip()
            if (
                self._looks_like_company(candidate, company)
                and candidate.lower() not in {company.lower(), *[n.lower() for n in names]}
            ):
                names.append(candidate)
            if len(names) == 3:
                break
        return names

    def search_competitor_evidence(self, company: str) -> list[SearchResult]:
        return self.search(f"top competitors of {company} market alternatives companies")

    @staticmethod
    def _looks_like_company(candidate: str, company: str) -> bool:
        """Reject article/list headlines before they enter the competitor queue."""
        normalized = candidate.lower()
        blocked_terms = (
            "alternative",
            "competitor",
            "top ",
            "best ",
            "for 20",
            "review",
            "comparison",
            "guide",
        )
        if not candidate or normalized == company.lower():
            return False
        if any(term in normalized for term in blocked_terms):
            return False
        if len(candidate.split()) > 6 or len(candidate) > 60:
            return False
        return bool(re.search(r"[a-zA-Z]", candidate))

    def parallel_research(self, competitor: str) -> dict[str, list[SearchResult]]:
        queries = {
            "web": f"{competitor} pricing features product positioning",
            "news": f"{competitor} latest news announcements funding product updates",
        }
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                kind: executor.submit(self.search, query, freshness="day" if kind == "news" else None)
                for kind, query in queries.items()
            }
            return {kind: future.result() for kind, future in futures.items()}

    @staticmethod
    def _parse_results(payload: dict[str, Any]) -> list[SearchResult]:
        raw_results: Any = payload.get("results", payload.get("web", []))
        if isinstance(raw_results, dict):
            raw_results = raw_results.get(
                "web", raw_results.get("results", raw_results.get("items", []))
            )
        if isinstance(raw_results, dict):
            raw_results = raw_results.get("results", raw_results.get("items", []))
        parsed: list[SearchResult] = []
        for item in raw_results or []:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url", item.get("link", "")))
            title = str(item.get("title", "Untitled result"))
            if not url:
                continue
            parsed.append(
                SearchResult(
                    title=title,
                    url=url,
                    snippet=str(item.get("description", item.get("snippet", ""))),
                    source=str(item.get("source", "")),
                    published_date=item.get("published_date", item.get("date")),
                )
            )
        return parsed[:8]
