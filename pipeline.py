from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from analyst import CompetitorAnalyst
from models import CompetitorReport, ResearchState
from youcom_client import YouComClient


class CompetitiveResearchPipeline:
    def __init__(self, search_client: YouComClient, analyst: CompetitorAnalyst) -> None:
        self.search_client = search_client
        self.analyst = analyst
        self.graph = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(ResearchState)
        workflow.add_node("discover", self._discover)
        workflow.add_node("researcher", self._researcher)
        workflow.add_node("analyst", self._analyst)
        workflow.add_edge(START, "discover")
        workflow.add_conditional_edges(
            "discover", self._queue_router, {"researcher": "researcher", "done": END}
        )
        workflow.add_edge("researcher", "analyst")
        workflow.add_conditional_edges(
            "analyst", self._queue_router, {"researcher": "researcher", "done": END}
        )
        return workflow.compile()

    def run(self, company: str) -> ResearchState:
        return self.graph.invoke(
            {
                "company": company.strip(),
                "competitor_queue": [],
                "reports": [],
                "search_results": {},
                "status": "starting",
                "error": None,
            }
        )

    def _discover(self, state: ResearchState) -> dict:
        company = state["company"]
        if hasattr(self.search_client, "search_competitor_evidence") and hasattr(
            self.analyst, "discover_competitors"
        ):
            evidence = self.search_client.search_competitor_evidence(company)
            competitors = self.analyst.discover_competitors(company, evidence)
        else:
            competitors = self.search_client.search_competitors(company)
        return {
            "competitor_queue": competitors[:3],
            "reports": [],
            "status": f"Found {len(competitors[:3])} competitors",
        }

    def _researcher(self, state: ResearchState) -> dict:
        queue = list(state.get("competitor_queue", []))
        if not queue:
            return {"status": "No competitors found"}
        competitor = queue.pop(0)
        results = self.search_client.parallel_research(competitor)
        return {
            "competitor_queue": queue,
            "current_competitor": competitor,
            "search_results": results,
            "status": f"Researched {competitor}",
        }

    def _analyst(self, state: ResearchState) -> dict:
        competitor = state["current_competitor"]
        report = self.analyst.analyze(
            state["company"], competitor, state.get("search_results", {})
        )
        return {"reports": [*state.get("reports", []), report]}

    @staticmethod
    def _queue_router(state: ResearchState) -> str:
        return "researcher" if state.get("competitor_queue") else "done"
