from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import re
from urllib.parse import urlsplit
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

    def search(self, query: str, *, freshness: str | None = None, category: str = "web") -> list[SearchResult]:
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
        return self._parse_results(response.json(), category=category)

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
                kind: executor.submit(self.search, query, freshness="month" if kind == "news" else None, category=kind)
                for kind, query in queries.items()
            }
            return {kind: future.result() for kind, future in futures.items()}

    @staticmethod
    def _parse_results(payload: dict[str, Any], category: str = "web") -> list[SearchResult]:
        if not isinstance(payload, dict):
            raise ValueError("You.com returned an invalid search response")
        raw_results: Any = payload.get("results", payload)
        if isinstance(raw_results, dict):
            raw_results = raw_results.get(category, raw_results.get("items", []))
        if isinstance(raw_results, dict):
            raw_results = raw_results.get("results", raw_results.get("items", []))
        if not isinstance(raw_results, list):
            raise ValueError("You.com returned an invalid result list")
        parsed: list[SearchResult] = []
        seen: set[str] = set()
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            url = item.get("url") or item.get("link")
            if not isinstance(url, str):
                continue
            try:
                parts = urlsplit(url)
                if parts.scheme not in {"http", "https"} or not parts.hostname:
                    continue
            except ValueError:
                continue
            if url in seen:
                continue
            seen.add(url)
            snippets = item.get("snippets") or []
            if isinstance(snippets, str):
                snippets = [snippets]
            if not isinstance(snippets, list):
                snippets = []
            text = [item.get("description") or item.get("snippet") or "", *snippets]
            snippet = " ".join(dict.fromkeys(part for part in text if isinstance(part, str) and part))
            date = item.get("published_date") or item.get("page_age") or item.get("date")
            parsed.append(SearchResult(
                title=str(item.get("title") or "Untitled result"),
                url=url,
                snippet=snippet[:6000],
                source=str(item.get("source") or ""),
                published_date=str(date) if date is not None else None,
            ))
        return parsed[:8]
