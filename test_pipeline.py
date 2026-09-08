import json

from models import CompetitorReport, SearchResult
from analyst import CompetitorAnalyst, ModelOutputError
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
    analyst = make_analyst('{"summary": "A competitor summary"}')
    report = analyst.analyze("Acme", "Figma", {
        "web": [SearchResult(title="Figma", url="https://example.com")]
    })
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


# Standard-library discovery runs every test, including the original smoke checks.
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch


def make_analyst(content):
    analyst = CompetitorAnalyst("test-placeholder", "test-model")
    analyst.llm = Mock()
    analyst.llm.invoke.return_value = SimpleNamespace(content=content)
    return analyst


def test_discovery_trims_deduplicates_and_excludes_target():
    analyst = make_analyst('[" Acme ", "Alpha", " alpha ", "Beta", "Gamma", "Delta"]')
    evidence = [SearchResult(title="Alternatives", url="https://example.com")]
    assert analyst.discover_competitors(" Acme ", evidence) == ["Alpha", "Beta", "Gamma"]


def test_empty_evidence_skips_model():
    analyst = make_analyst("invalid")
    assert analyst.discover_competitors("Acme", []) == []
    report = analyst.analyze("Acme", "Alpha", {"web": [], "news": []})
    assert report.summary == "Evidence unavailable"
    analyst.llm.invoke.assert_not_called()


def test_analyze_fixes_identity_and_filters_unsupported_urls():
    analyst = make_analyst(json.dumps({
        "name": "Wrong", "website": "https://invented.example",
        "sources": ["https://example.com", "https://invented.example", "https://example.com"]
    }))
    report = analyst.analyze("Acme", "Alpha", {
        "web": [SearchResult(title="Alpha", url="https://example.com")]
    })
    assert report.name == "Alpha"
    assert report.website == ""
    assert report.sources == ["https://example.com"]


def test_malformed_model_output_fails():
    analyst = make_analyst("not JSON")
    with unittest.TestCase().assertRaises(ValueError):
        analyst.analyze("Acme", "Alpha", {
            "web": [SearchResult(title="Alpha", url="https://example.com")]
        })


def test_blank_input_rejected_before_search():
    search = Mock()
    with unittest.TestCase().assertRaises(ValueError):
        CompetitiveResearchPipeline(search, FakeAnalyst()).run(" ")
    search.search_competitor_evidence.assert_not_called()


def test_production_discovery_path_and_final_status():
    search = Mock()
    search.search_competitor_evidence.return_value = []
    search.parallel_research.return_value = {"web": [], "news": []}
    analyst = Mock()
    analyst.discover_competitors.return_value = [" Acme ", "Alpha", " alpha ", "Beta"]
    analyst.analyze.side_effect = lambda company, name, evidence: CompetitorReport(name=name)
    result = CompetitiveResearchPipeline(search, analyst).run(" Acme ")
    assert [r.name for r in result["reports"]] == ["Alpha", "Beta"]
    assert result["status"] == "Research complete: 2 reports"
    search.search_competitors.assert_not_called()


def test_search_parser_preserves_news_snippets_dates_and_web_separation():
    payload = {"results": {
        "web": [{"title": "Product", "url": "https://example.com/product"}],
        "news": [{"title": "Launch", "url": "https://example.com/news",
                  "description": "Summary", "snippets": ["Details"], "page_age": "2026-09-01"}],
    }}
    news = YouComClient._parse_results(payload, "news")
    assert len(news) == 1
    assert news[0].snippet == "Summary Details"
    assert news[0].published_date == "2026-09-01"
    assert YouComClient._parse_results(payload)[0].title == "Product"
    assert YouComClient._parse_results({"results": {"web": []}}, "news") == []


def test_search_parser_skips_bad_urls_and_duplicates():
    results = YouComClient._parse_results({"web": [
        {"url": None}, {"url": "javascript:alert(1)"}, {"url": "https://"},
        {"url": "https://example.com"}, {"url": "https://example.com"}
    ]})
    assert len(results) == 1


def test_search_auth_errors_and_request_contract():
    for code in (401, 403):
        response = Mock(status_code=code)
        with patch("youcom_client.requests.post", return_value=response) as post:
            with unittest.TestCase().assertRaisesRegex(Exception, str(code)):
                YouComClient("placeholder").search("Acme")
            assert post.call_args.kwargs["json"] == {"query": "Acme"}
            assert post.call_args.kwargs["timeout"] == 12


def test_parallel_research_selects_news_section():
    client = YouComClient("placeholder")
    client.search = Mock(return_value=[])
    assert client.parallel_research("Alpha") == {"web": [], "news": []}
    kwargs = [call.kwargs for call in client.search.call_args_list]
    assert {"category": "news", "freshness": "month"} in kwargs
    assert {"category": "web", "freshness": None} in kwargs


def test_ui_keeps_snapshot_identity_and_escapes_model_html():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file("app.py", default_timeout=10)
    app.session_state["reports"] = [CompetitorReport(name="<b>Alpha</b>", summary="<img src=x>")]
    app.session_state["report_company"] = "Acme"
    app.run()
    app.text_input[0].set_value("Different company").run()
    assert not app.exception
    markup = "\n".join(element.value for element in app.markdown)
    assert "Competitive snapshot for Acme" in markup
    assert "&lt;b&gt;Alpha&lt;/b&gt;" in markup
    assert "<img src=x>" not in markup
    app.text_input[0].set_value("")
    app.button[0].click().run()
    assert "reports" not in app.session_state



def test_analyst_retries_empty_prose_and_truncated_outputs():
    evidence = {"web": [SearchResult(title="Alpha", url="https://example.com")]}
    for invalid in ("", "Here is my analysis.", '{"summary":', '{"summary":"ok","name":'):
        analyst = make_analyst(invalid)
        analyst.llm.invoke.side_effect = [
            SimpleNamespace(content=invalid),
            SimpleNamespace(content='{"summary": "Recovered"}'),
        ]
        assert analyst.analyze("Acme", "Alpha", evidence).summary == "Recovered"
        assert analyst.llm.invoke.call_count == 2
        retry = analyst.llm.invoke.call_args.args[0]
        assert "previous response" in retry[-1].content
        assert "https://example.com" in retry[1].content


def test_response_text_blocks_are_parsed_without_retry():
    analyst = make_analyst([
        {"type": "reasoning", "text": "This is not report JSON"},
        {"type": "text", "text": '{"summary":'},
        {"type": "text", "text": '"Block content"}'},
    ])
    report = analyst.analyze("Acme", "Alpha", {
        "web": [SearchResult(title="Alpha", url="https://example.com")]
    })
    assert report.summary == "Block content"
    assert analyst.llm.invoke.call_count == 1


def test_json_parser_handles_fences_escaped_braces_and_trailing_commentary():
    raw = 'Preface\n```json\n{"summary": "Text with } brace"}\n```\nTrailing {comment}'
    assert json.loads(CompetitorAnalyst._extract_json(raw))["summary"] == "Text with } brace"
    with unittest.TestCase().assertRaises(ValueError):
        CompetitorAnalyst._extract_json('[{"summary": "Wrong container"}]')


def test_discovery_retries_invalid_response():
    analyst = make_analyst("")
    analyst.llm.invoke.side_effect = [
        SimpleNamespace(content="Alpha and Beta"),
        SimpleNamespace(content='["Alpha", "Beta"]'),
    ]
    assert analyst.discover_competitors("Acme", [
        SearchResult(title="Alternatives", url="https://example.com")
    ]) == ["Alpha", "Beta"]
    assert analyst.llm.invoke.call_count == 2


def test_output_retries_are_bounded_and_actionable():
    analyst = make_analyst(None)
    with unittest.TestCase().assertRaisesRegex(ModelOutputError, "after two attempts"):
        analyst.analyze("Acme", "Alpha", {
            "web": [SearchResult(title="Alpha", url="https://example.com")]
        })
    assert analyst.llm.invoke.call_count == 2


def test_provider_errors_are_not_retried_as_json_errors():
    analyst = make_analyst("")
    analyst.llm.invoke.side_effect = RuntimeError("provider unavailable")
    with unittest.TestCase().assertRaisesRegex(RuntimeError, "provider unavailable"):
        analyst.discover_competitors("Acme", [
            SearchResult(title="Alternatives", url="https://example.com")
        ])
    assert analyst.llm.invoke.call_count == 1


def test_analyst_preserves_homepage_supported_by_retrieved_subpage():
    analyst = make_analyst('{"website":"https://alpha.example/","summary":"Design tools"}')
    report = analyst.analyze("Acme", "Alpha", {
        "web": [SearchResult(title="Alpha pricing", url="https://alpha.example/pricing")]
    })
    assert report.website == "https://alpha.example/"
    assert not analyst._website_supported("https://alpha.example/invented", {"https://alpha.example/pricing"})
    assert not analyst._website_supported("https://invented.example/", {"https://alpha.example/pricing"})


def test_analyst_unwraps_report_instead_of_returning_empty_defaults():
    for wrapper in ("report", "competitor_report", "analysis"):
        analyst = make_analyst(json.dumps({
            wrapper: {"summary": "Design platform", "features": ["Collaboration"]}
        }))
        report = analyst.analyze("Acme", "Alpha", {
            "web": [SearchResult(title="Alpha", url="https://example.com")]
        })
        assert report.summary == "Design platform"
        assert report.features == ["Collaboration"]


def test_analyst_retries_unrecognized_envelope_instead_of_empty_report():
    analyst = make_analyst("")
    analyst.llm.invoke.side_effect = [
        SimpleNamespace(content='{"unexpected": {"summary": "Hidden"}}'),
        SimpleNamespace(content='{"summary": "Recovered evidence"}'),
    ]
    report = analyst.analyze("Acme", "Alpha", {
        "web": [SearchResult(title="Alpha", url="https://example.com")]
    })
    assert report.summary == "Recovered evidence"
    assert analyst.llm.invoke.call_count == 2


def test_analyst_retries_all_unavailable_despite_real_evidence():
    analyst = make_analyst("")
    analyst.llm.invoke.side_effect = [
        SimpleNamespace(content='{"summary":"Evidence unavailable","features":[]}'),
        SimpleNamespace(content='{"summary":"Collaborative design","features":["Team editing"]}'),
    ]
    report = analyst.analyze("Acme", "Alpha", {
        "web": [SearchResult(title="Alpha", url="https://example.com",
                             snippet="Alpha offers collaborative design with team editing.")]
    })
    assert report.features == ["Team editing"]
    assert analyst.llm.invoke.call_count == 2


def test_analyst_does_not_present_repeated_empty_analysis_as_success():
    analyst = make_analyst('{"summary":"Evidence unavailable","features":[]}')
    with unittest.TestCase().assertRaises(ModelOutputError):
        analyst.analyze("Acme", "Alpha", {
            "web": [SearchResult(title="Alpha", url="https://example.com", snippet="Team editing")]
        })
    assert analyst.llm.invoke.call_count == 2


def test_worker_deadline_terminates_slow_provider():
    import sys, time, subprocess
    from research_runner import _run_worker, ResearchRunError
    real_popen = subprocess.Popen
    processes = []
    def capture(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        processes.append(process)
        return process
    start = time.monotonic()
    with patch("research_runner.subprocess.Popen", side_effect=capture):
        with unittest.TestCase().assertRaisesRegex(ResearchRunError, "took too long"):
            _run_worker({}, 0.3, command=[sys.executable, "-c", "import time; time.sleep(20)"])
    assert time.monotonic() - start < 3
    assert processes[0].poll() is not None


def test_worker_progress_and_result_round_trip():
    import sys
    from research_runner import _run_worker
    script = 'import json; print(json.dumps({"type":"progress","message":"Analyzing Alpha"}),flush=True); print(json.dumps({"type":"result","result":{"company":"Acme","reports":[{"name":"Alpha"}]}}),flush=True)'
    progress = []
    result = _run_worker({}, 5, progress.append, [sys.executable, "-c", script])
    assert progress == ["Analyzing Alpha"]
    assert result["reports"][0].name == "Alpha"


def test_worker_failure_is_actionable():
    import sys
    from research_runner import _run_worker, ResearchRunError
    with unittest.TestCase().assertRaisesRegex(ResearchRunError, "without a result"):
        _run_worker({}, 5, command=[sys.executable, "-c", "pass"])


def test_ui_uses_deadline_runner_and_displays_result():
    from streamlit.testing.v1 import AppTest
    def fake_run(*args, **kwargs):
        kwargs["on_progress"]("Analyzing Alpha")
        return {"company": "Acme", "reports": [CompetitorReport(name="Alpha", summary="Team design")]}
    with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-placeholder", "YDC_API_KEY": "test-placeholder"}):
        with patch("research_runner.run_research", side_effect=fake_run):
            app = AppTest.from_file("app.py", default_timeout=10).run()
            app.text_input[0].set_value("Acme")
            app.button[0].click().run()
            assert not app.exception
            assert app.session_state["reports"][0].name == "Alpha"


def test_ui_displays_deadline_error_without_traceback():
    from streamlit.testing.v1 import AppTest
    from research_runner import ResearchRunError
    with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-placeholder", "YDC_API_KEY": "test-placeholder"}):
        with patch("research_runner.run_research", side_effect=ResearchRunError("Research stopped after 120 seconds.")):
            app = AppTest.from_file("app.py", default_timeout=10).run()
            app.text_input[0].set_value("Acme")
            app.button[0].click().run()
            assert not app.exception
            assert any("120 seconds" in e.value for e in app.error)


def test_analysis_requests_strict_schema_and_compatible_provider():
    analyst = make_analyst('{"summary":"Design tools"}')
    analyst.analyze("Acme", "Alpha", {"web": [SearchResult(title="Alpha",url="https://example.com")]})
    options = analyst.llm.invoke.call_args.kwargs
    schema = options["response_format"]["json_schema"]
    assert schema["strict"] is True
    assert schema["schema"]["additionalProperties"] is False
    assert set(schema["schema"]["required"]) == set(CompetitorReport.model_fields)
    assert options["extra_body"]["provider"]["require_parameters"] is True


def test_discovery_accepts_schema_object():
    analyst = make_analyst('{"competitors":["Alpha","Beta"]}')
    assert analyst.discover_competitors("Acme", [SearchResult(title="Alternatives",url="https://example.com")]) == ["Alpha","Beta"]
    assert analyst.llm.invoke.call_args.kwargs["response_format"]["json_schema"]["schema"]["required"] == ["competitors"]


def test_truncated_json_is_not_accepted_even_when_parseable():
    analyst = make_analyst("")
    analyst.llm.invoke.side_effect = [
        SimpleNamespace(content='{"summary":"Partial"}',response_metadata={"finish_reason":"length"}),
        SimpleNamespace(content='{"summary":"Complete"}',response_metadata={"finish_reason":"stop"}),
    ]
    report = analyst.analyze("Acme", "Alpha", {"web":[SearchResult(title="Alpha",url="https://example.com")]})
    assert report.summary == "Complete"
    assert analyst.llm.invoke.call_count == 2


def test_schema_compatibility_fallback_is_bounded():
    class UnsupportedSchema(Exception):
        status_code = 404
    analyst = make_analyst("")
    analyst.llm.invoke.side_effect = [
        UnsupportedSchema(), SimpleNamespace(content='{"summary":"Design tools"}'),
    ]
    report = analyst.analyze("Acme", "Alpha", {"web":[SearchResult(title="Alpha",url="https://example.com")]})
    assert report.summary == "Design tools"
    calls = analyst.llm.invoke.call_args_list
    assert calls[0].kwargs["response_format"]["type"] == "json_schema"
    assert calls[1].kwargs["response_format"]["type"] == "json_object"
    assert len(calls) == 2


def test_rate_limit_does_not_trigger_format_fallback():
    class RateLimit(Exception):
        status_code = 429
    analyst = make_analyst("")
    analyst.llm.invoke.side_effect = RateLimit()
    with unittest.TestCase().assertRaises(RateLimit):
        analyst.discover_competitors("Acme", [SearchResult(title="Alternatives",url="https://example.com")])
    assert analyst.llm.invoke.call_count == 1


def test_format_fallback_is_reused_with_local_validation():
    class UnsupportedSchema(Exception):
        status_code = 404
    analyst = make_analyst("")
    analyst.llm.invoke.side_effect = [
        UnsupportedSchema(), SimpleNamespace(content='{"summary":"Design tools"}'),
        SimpleNamespace(content='{"summary":"Team tools"}'),
    ]
    evidence = {"web":[SearchResult(title="Alpha",url="https://example.com")]}
    analyst.analyze("Acme", "Alpha", evidence)
    report = analyst.analyze("Acme", "Beta", evidence)
    assert report.summary == "Team tools"
    assert analyst.llm.invoke.call_count == 3
    options = analyst.llm.invoke.call_args.kwargs
    assert options["response_format"]["type"] == "json_object"
    assert options["extra_body"]["provider"]["require_parameters"] is False


def test_sdk_truncation_retries_with_larger_output_budget():
    from openai import LengthFinishReasonError
    from openai.types.chat import ChatCompletion
    completion = ChatCompletion(id="test",created=0,model="test",object="chat.completion",choices=[])
    analyst = make_analyst("")
    analyst.llm.invoke.side_effect = [
        LengthFinishReasonError(completion=completion),
        SimpleNamespace(content='{"summary":"Complete report"}'),
    ]
    report = analyst.analyze("Acme", "Alpha", {"web":[SearchResult(title="Alpha",url="https://example.com")]})
    assert report.summary == "Complete report"
    calls = analyst.llm.invoke.call_args_list
    assert calls[0].kwargs["max_tokens"] == 4096
    assert calls[1].kwargs["max_tokens"] == 8192

def test_pipeline_respects_scope_and_emits_completed_reports():
    emitted = []
    result = CompetitiveResearchPipeline(FakeSearchClient(), FakeAnalyst(),
        max_competitors=1, on_report=emitted.append).run("Acme")
    assert [r.name for r in result["reports"]] == ["Alpha"]
    assert emitted == result["reports"]


def test_worker_keeps_report_after_timeout_and_terminates_process():
    import sys, time, subprocess
    from research_runner import _run_worker
    script = 'import json,time; print(json.dumps({"type":"report","report":{"name":"Alpha","summary":"Team tools"}}),flush=True); time.sleep(20)'
    processes = []
    real_popen = subprocess.Popen
    def capture(*args, **kwargs):
        p = real_popen(*args, **kwargs)
        processes.append(p)
        return p
    with patch("research_runner.subprocess.Popen", side_effect=capture):
        result = _run_worker({"company":"Acme","max_competitors":3}, 0.5,
                             command=[sys.executable, "-c", script])
    assert result["partial"] is True
    assert result["requested_competitors"] == 3
    assert result["reports"][0].name == "Alpha"
    assert "took too long" in result["status"]
    assert processes[0].poll() is not None


def test_worker_keeps_completed_report_after_provider_error():
    import sys
    from research_runner import _run_worker
    script = 'import json; print(json.dumps({"type":"report","report":{"name":"Alpha"}}),flush=True); print(json.dumps({"type":"error","message":"Provider unavailable"}),flush=True)'
    result = _run_worker({"company":"Acme"}, 5, command=[sys.executable,"-c",script])
    assert result["partial"] is True
    assert result["status"] == "Provider unavailable"
    assert len(result["reports"]) == 1


def test_ui_preserves_partial_reports_and_scope():
    from streamlit.testing.v1 import AppTest
    def fake_run(*args, **kwargs):
        assert kwargs["max_competitors"] == 2
        return {"company":"Acme", "reports":[CompetitorReport(name="Alpha")],
                "partial":True, "status":"Provider took too long", "requested_competitors":2}
    with patch.dict("os.environ", {"OPENROUTER_API_KEY":"test-placeholder", "YDC_API_KEY":"test-placeholder"}):
        with patch("research_runner.run_research", side_effect=fake_run):
            app = AppTest.from_file("app.py", default_timeout=10).run()
            assert app.selectbox[0].value == 1
            app.selectbox[0].select(2)
            app.text_input[0].set_value("Acme")
            app.button[0].click().run()
            assert not app.exception
            assert app.session_state["reports"][0].name == "Alpha"
            assert app.session_state["research_partial"] is True
            assert any("Partial research" in w.value for w in app.warning)


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(
        unittest.FunctionTestCase(function)
        for name, function in globals().items()
        if name.startswith("test_") and callable(function)
    )


if __name__ == "__main__":
    unittest.main()
