from __future__ import annotations

import json

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from models import CompetitorReport, SearchResult


class CompetitorAnalyst:
    """Uses OpenRouter's OpenAI-compatible API with a compact ReAct-style prompt."""

    def __init__(self, api_key: str, model: str, app_url: str = "", app_name: str = "Market Signal") -> None:
        self.llm = ChatOpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            model=model,
            temperature=0,
            default_headers={
                "HTTP-Referer": app_url,
                "X-Title": app_name,
            },
        )
        self.prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """You are a competitive intelligence analyst. Use the supplied fresh search evidence only.
Reason in a concise ReAct style internally: identify gaps, weigh evidence, then produce the final JSON.
                    "Never invent facts. Use 'Evidence unavailable' when a text field has no support, "
                    "and use an empty array when a list has no support.\n"
                    "Return every field in this exact JSON shape: name, website, summary, positioning, "
                    "pricing, features, recent_news, strengths, watchouts, sources. "
                    "Positioning must be a concise string. Return JSON only, with no markdown.""",
                ),
                ("human", "Company: {company}\nCompetitor: {competitor}\nEvidence:\n{evidence}"),
            ]
        )
        self.discovery_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "Extract exactly three real competitor company names from the search evidence. "
                    "Ignore article titles, list headlines, publishers, and the target company. "
                    "Return only a JSON array of strings, with no markdown.",
                ),
                ("human", "Target company: {company}\nSearch evidence:\n{evidence}"),
            ]
        )

    def discover_competitors(
        self, company: str, results: list[SearchResult]
    ) -> list[str]:
        evidence = "\n".join(
            f"- {item.title}: {item.snippet} ({item.url})" for item in results
        )
        response = self.llm.invoke(
            self.discovery_prompt.format_messages(company=company, evidence=evidence)
        )
        content = response.content if isinstance(response.content, str) else str(response.content)
        raw = self._extract_json_array(content)
        names: list[str] = []
        for value in json.loads(raw):
            if isinstance(value, str) and value.strip() and value.lower() != company.lower():
                if value.strip().lower() not in {name.lower() for name in names}:
                    names.append(value.strip())
        return names[:3]

    def analyze(
        self,
        company: str,
        competitor: str,
        results: dict[str, list[SearchResult]],
    ) -> CompetitorReport:
        evidence = self._format_evidence(results)
        response = self.llm.invoke(
            self.prompt.format_messages(
                company=company, competitor=competitor, evidence=evidence
            )
        )
        content = response.content if isinstance(response.content, str) else str(response.content)
        report_data = json.loads(self._extract_json(content))
        report_data.setdefault("name", report_data.get("competitor", competitor))
        report_data.setdefault("positioning", report_data.get("summary", "Evidence unavailable"))
        return CompetitorReport.model_validate(report_data)

    @staticmethod
    def _format_evidence(results: dict[str, list[SearchResult]]) -> str:
        chunks: list[str] = []
        for category, items in results.items():
            chunks.append(f"[{category.upper()}]")
            for item in items:
                chunks.append(f"- {item.title}: {item.snippet} ({item.url})")
        return "\n".join(chunks) or "No search evidence returned."

    @staticmethod
    def _extract_json(content: str) -> str:
        content = content.strip()
        if content.startswith("```"):
            content = content.strip("`").removeprefix("json").strip()
        start, end = content.find("{"), content.rfind("}")
        if start < 0 or end < start:
            raise ValueError("Analyst did not return a JSON object")
        return content[start : end + 1]

    @staticmethod
    def _extract_json_array(content: str) -> str:
        start, end = content.find("["), content.rfind("]")
        if start < 0 or end < start:
            raise ValueError("Competitor discovery did not return a JSON array")
        return content[start : end + 1]
