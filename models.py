from __future__ import annotations

from typing import Any, Optional, TypedDict

from pydantic import BaseModel, Field, field_validator


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str = ""
    source: str = ""
    published_date: Optional[str] = None


class CompetitorReport(BaseModel):
    name: str
    website: str = ""
    summary: str = ""
    positioning: str = ""
    pricing: list[str] = Field(default_factory=list)
    features: list[str] = Field(default_factory=list)
    recent_news: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    watchouts: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)

    @field_validator("website", "summary", "positioning", mode="before")
    @classmethod
    def normalize_text_fields(cls, value: Any) -> str:
        """Convert structured text returned by an LLM into displayable text."""
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            return "; ".join(f"{key}: {item}" for key, item in value.items())
        if isinstance(value, list):
            return "; ".join(cls._item_to_text(item) for item in value)
        return str(value)

    @field_validator(
        "pricing",
        "features",
        "recent_news",
        "strengths",
        "watchouts",
        "sources",
        mode="before",
    )
    @classmethod
    def normalize_list_fields(cls, value: Any) -> list[str]:
        """Accept list, string, and common nested objects returned by LLMs."""
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            if len(value) == 1:
                value = next(iter(value.values()))
            else:
                value = [value]
        if not isinstance(value, list):
            return [str(value)]
        return [cls._item_to_text(item) for item in value]

    @staticmethod
    def _item_to_text(item: Any) -> str:
        if isinstance(item, str):
            return item
        if isinstance(item, dict):
            preferred_keys = ("name", "title", "description", "price", "url")
            preferred = [str(item[key]) for key in preferred_keys if item.get(key)]
            if preferred:
                return " | ".join(preferred)
            return "; ".join(f"{key}: {value}" for key, value in item.items())
        return str(item)


class ResearchState(TypedDict, total=False):
    company: str
    competitor_queue: list[str]
    current_competitor: Optional[str]
    search_results: dict[str, list[SearchResult]]
    reports: list[CompetitorReport]
    status: str
    error: Optional[str]
