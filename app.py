from __future__ import annotations

import os
import json
from html import escape

import streamlit as st
from dotenv import load_dotenv

from analyst import ModelOutputError
from research_runner import run_research, ResearchRunError

load_dotenv()
st.set_page_config(page_title="Market Signal", page_icon="◈", layout="wide")

st.markdown(
    """
    <style>
    :root { --ink: #19231d; --mint: #d9f2df; --acid: #b7e85d; --paper: #f6f7f1; }
    .stApp { background: var(--paper); color: var(--ink); }
    .hero { padding: 2.5rem 0 1.5rem; border-bottom: 1px solid #cbd5c6; }
    .eyebrow { color: #52705a; font-size: .78rem; letter-spacing: .14em; text-transform: uppercase; font-weight: 700; }
    .hero h1 { font-size: clamp(2.5rem, 6vw, 5.6rem); line-height: .95; letter-spacing: -.04em; margin: .4rem 0 1rem; max-width: 850px; }
    .hero p { max-width: 650px; font-size: 1.05rem; color: #536259; }
    .report { background: white; border: 1px solid #d8e0d3; border-radius: 8px; padding: 1.35rem; margin: 1rem 0; box-shadow: 0 10px 30px rgba(34, 55, 39, .06); }
    .report h3 { margin: 0; font-size: 1.45rem; }
    .tag { display: inline-block; background: var(--mint); border-radius: 99px; padding: .25rem .6rem; margin: .7rem .3rem 0 0; font-size: .8rem; }
    .source { color: #52705a; font-size: .84rem; }
    .flow-node { border: 1px solid #cbd8c8; border-radius: 6px; padding: .55rem .7rem; margin: .35rem 0; background: #fbfcf8; }
    .flow-node strong { color: #213d2a; }
    .flow-arrow { color: #6c8b70; text-align: center; line-height: 1; }
    .flow-detail { color: #617067; font-size: .78rem; margin-top: .15rem; }
    .flow-group { color: #52705a; font-size: .7rem; letter-spacing: .1em; text-transform: uppercase; font-weight: 700; margin-top: .9rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="hero"><div class="eyebrow">Market intelligence / live web signals</div>'
    '<h1>See who is moving around your market.</h1>'
    '<p>Discover up to three competitors, scan current web and news evidence, and turn it into decision-ready research cards.</p></div>',
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("### Research controls")
    company = st.text_input("Company to investigate", placeholder="e.g. Figma")
    run = st.button("Run research pipeline", type="primary", use_container_width=True)
    st.caption("Fresh searches are run live. Reports are generated for this session only.")
    with st.expander("Complete pipeline architecture", expanded=True):
        st.markdown(
            """
            <div class="flow-group">Input and orchestration</div>
            <div class="flow-node"><strong>Streamlit UI</strong><div class="flow-detail">Company input, credentials check, progress status, and report cards.</div></div>
            <div class="flow-arrow">↓</div>
            <div class="flow-node"><strong>LangGraph orchestrator</strong><div class="flow-detail">Runs the discover → research → analyze graph and controls the queue loop.</div></div>

            <div class="flow-group">Graph nodes</div>
            <div class="flow-node"><strong>1. Discovery node</strong><div class="flow-detail">You.com returns fresh evidence. OpenRouter extracts up to three real competitor companies.</div></div>
            <div class="flow-arrow">↓</div>
            <div class="flow-node"><strong>2. Queue router</strong><div class="flow-detail">Sends the next competitor to research. When the queue is empty, the workflow ends.</div></div>
            <div class="flow-arrow">↺</div>
            <div class="flow-node"><strong>3. Researcher node</strong><div class="flow-detail">Processes one competitor at a time and combines web and news search results.</div></div>
            <div class="flow-arrow">↓</div>
            <div class="flow-node"><strong>4. Analyst node</strong><div class="flow-detail">OpenRouter converts evidence into a validated competitor report.</div></div>

            <div class="flow-group">You.com tool layer</div>
            <div class="flow-node"><strong>Web search</strong><div class="flow-detail">Pricing, features, product, and positioning.</div></div>
            <div class="flow-node"><strong>News search</strong><div class="flow-detail">Recent announcements, funding, and product updates.</div></div>

            <div class="flow-group">Terminal output</div>
            <div class="flow-node"><strong>Competitor report cards</strong><div class="flow-detail">Pricing, features, positioning, news, strengths, watchouts, and sources.</div></div>
            <div class="flow-detail">Report-only workflow: no emails, database writes, or business actions.</div>
            """
            , unsafe_allow_html=True
        )

if run:
    for key in ("reports", "research_status", "report_company"):
        st.session_state.pop(key, None)
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    you_key = os.getenv("YDC_API_KEY")
    if not company.strip():
        st.error("Enter a company name first.")
    elif not openrouter_key or not you_key:
        st.error("Add OPENROUTER_API_KEY and YDC_API_KEY to your .env file before running live research.")
    else:
        with st.status("Running live market research...", expanded=True) as status:
            try:
                st.caption("Research has a two-minute limit.")
                result = run_research(
                    company, you_key, openrouter_key,
                    os.getenv("OPENROUTER_MODEL", "openrouter/free"),
                    os.getenv("APP_URL", "http://localhost:8501"),
                    os.getenv("YDC_SEARCH_ENDPOINT"),
                    on_progress=lambda message: status.update(label=message),
                )
                status.update(label="Research complete", state="complete", expanded=False)
                st.session_state["report_company"] = result["company"]
                st.session_state["reports"] = result.get("reports", [])
                st.session_state["research_status"] = result.get("status", "")
            except Exception as exc:
                status.update(label="Research failed", state="error")
                if isinstance(exc, (ModelOutputError, ResearchRunError)):
                    st.error(str(exc))
                elif "402" in str(exc) and ("Insufficient Balance" in str(exc) or "credits" in str(exc).lower()):
                    st.error(
                        "OpenRouter rejected the request because this API key has no credits. "
                        "Add credits to OpenRouter or choose a funded model, then run the pipeline again."
                    )
                elif "401" in str(exc) and "YDC_API_KEY" in str(exc):
                    st.error(
                        "You.com rejected YDC_API_KEY. Create a valid You.com Search API key "
                        "and replace YDC_API_KEY in your .env file."
                    )
                elif "403" in str(exc) and "You.com denied access" in str(exc):
                    st.error(
                        "You.com denied access to Search API. Enable Search API access or add API credits "
                        "to the You.com account that owns YDC_API_KEY."
                    )
                else:
                    st.exception(exc)

reports = st.session_state.get("reports", [])
if reports:
    st.markdown(f"### Competitive snapshot for {st.session_state.get('report_company', '')}")
    st.caption(f"{len(reports)} structured reports generated from live web and news searches.")
    st.download_button(
        "Download JSON report",
        data=json.dumps({
            "company": st.session_state.get("report_company", ""),
            "reports": [report.model_dump() for report in reports],
        }, indent=2),
        file_name="competitive-research.json",
        mime="application/json",
    )
    for report in reports:
        st.markdown(
            f'<div class="report"><h3>{escape(report.name)}</h3>'
            f'<p>{escape(report.summary)}</p>'
            f'<span class="tag">{escape(report.positioning or report.summary or "Evidence unavailable")}</span></div>',
            unsafe_allow_html=True,
        )
        with st.expander(f"Open {report.name} analysis"):
            analysis_rows = [
                {"Category": "Website", "Findings": report.website or "Evidence unavailable"},
                {"Category": "Positioning", "Findings": report.positioning or report.summary or "Evidence unavailable"},
                {"Category": "Pricing", "Findings": "\n".join(report.pricing) or "Evidence unavailable"},
                {"Category": "Core features", "Findings": "\n".join(report.features) or "Evidence unavailable"},
                {"Category": "Strengths", "Findings": "\n".join(report.strengths) or "Evidence unavailable"},
                {"Category": "Watchouts", "Findings": "\n".join(report.watchouts) or "Evidence unavailable"},
                {"Category": "Recent news", "Findings": "\n".join(report.recent_news) or "Evidence unavailable"},
            ]
            st.table(analysis_rows)
            st.markdown("**Sources**")
            for source in report.sources:
                st.markdown(f'<div class="source">{escape(source)}</div>', unsafe_allow_html=True)
else:
    status_message = st.session_state.get("research_status")
    if status_message:
        st.warning(f"{status_message}. No competitor cards were generated.")
    else:
        st.info("Enter a company in the sidebar to generate the first snapshot.")
