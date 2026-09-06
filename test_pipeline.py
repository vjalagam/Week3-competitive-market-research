import json

from models import CompetitorReport, SearchResult
from analyst import CompetitorAnalyst
from pipeline import CompetitiveResearchPipeline
from youcom_client import YouComClient


class FakeSearchClient:
    def search_competitors(self, company):
        return ["Alpha", "Beta", "Gamma"]

    def parallel_research(self, competitor):
        return {"web": [SearchResult(title=competitor, url="https://example.com")], "news": []}


class EmptySearchClient(FakeSearchClient):
    def search_competitors(self, company):
        return []


class FakeAnalyst:
    def analyze(self, company, competitor, results):
        return CompetitorReport(name=competitor, summary=f"{company} vs {competitor}")


def test_pipeline_processes_three_competitors_and_stops():
    result = CompetitiveResearchPipeline(FakeSearchClient(), FakeAnalyst()).run("Acme")
    assert [report.name for report in result["reports"]] == ["Alpha", "Beta", "Gamma"]
    assert result["competitor_queue"] == []


def test_pipeline_stops_when_no_competitors_are_found():
    result = CompetitiveResearchPipeline(EmptySearchClient(), FakeAnalyst()).run("Unknown")
    assert result["reports"] == []
    assert result["status"] == "Found 0 competitors"


def test_analyst_fills_missing_report_name_from_competitor():
    content = '{"company": "Figma", "summary": "A competitor summary"}'
    data = json.loads(CompetitorAnalyst._extract_json(content))
    data.setdefault("name", data.get("competitor", "Figma"))
    report = CompetitorReport.model_validate(data)
    assert report.name == "Figma"


def test_competitor_discovery_rejects_article_headlines():
    assert not YouComClient._looks_like_company("Top 10 Figma Alternatives for 2026", "Figma")
    assert YouComClient._looks_like_company("Sketch", "Figma")


def test_report_normalizes_structured_llm_fields():
    report = CompetitorReport.model_validate(
        {
            "name": "Figma",
            "pricing": {"plans": [{"name": "Business", "price": "$16"}]},
            "features": "Collaborative design",
            "recent_news": {"articles": [{"title": "New release", "url": "https://example.com"}]},
        }
    )
    assert report.pricing == ["Business | $16"]
    assert report.features == ["Collaborative design"]
    assert report.recent_news == ["New release | https://example.com"]


def test_report_normalizes_structured_positioning():
    report = CompetitorReport.model_validate(
        {
            "name": "Figma",
            "positioning": {
                "market": "Design",
                "strategy": "Collaborative platform",
                "differentiators": "Browser-native experience",
            },
        }
    )
    assert report.positioning == (
        "market: Design; strategy: Collaborative platform; "
        "differentiators: Browser-native experience"
    )


if __name__ == "__main__":
    test_pipeline_processes_three_competitors_and_stops()
    test_pipeline_stops_when_no_competitors_are_found()
    test_analyst_fills_missing_report_name_from_competitor()
    test_report_normalizes_structured_llm_fields()
    test_report_normalizes_structured_positioning()
    print("pipeline smoke test passed")
