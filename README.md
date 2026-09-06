# Market Signal

Competitive market research with Streamlit, LangGraph, You.com Search API, and
OpenRouter. Enter a company to discover up to three competitors, research each
with parallel web/news searches, and view or download structured reports.

See [Project architecture and code review](PROJECT_ARCHITECTURE.md) for the
runtime diagram, component contracts, resolved gaps, and remaining limitations.
Download the [Word document](PROJECT_ARCHITECTURE.docx) or view the
[modern architecture diagram](architecture-flow.svg) ([PNG](architecture-flow.png)).

## Run locally

Python 3.12 is the tested runtime.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your own API keys.
streamlit run app.py
```

Set `OPENROUTER_API_KEY` and `YDC_API_KEY` in your local `.env`.
`OPENROUTER_MODEL` defaults to `openrouter/free`; you can select another
model supported by your OpenRouter account. Availability, limits, and charges
depend on your accounts and selected model. You.com requires its own Search
API access. Optional settings are documented in `.env.example`.

## Workflow

1. Discovery searches You.com and asks OpenRouter to extract competitor names.
2. LangGraph processes a queue of up to three unique competitors.
3. Each competitor gets concurrent web and news searches. News uses a month
   freshness filter and the API's news results.
4. OpenRouter synthesizes supplied evidence into a Pydantic-validated report.
5. Streamlit shows cards and provides a JSON download with the snapshot company.

The researcher uses direct API calls. There is no Groq integration, ReAct
tool agent, or academic search in the current implementation. The original
concept diagram is reconciled with the code in the architecture document.

Reports are held in the current session. New runs clear the previous snapshot.
Malformed model output is regenerated once using the original evidence. If
the second response is invalid, the UI suggests retrying or changing
`OPENROUTER_MODEL`. Provider failures stop the run; partial output is not recovered.
Empty evidence is shown as unavailable. Source URLs must come from retrieved
evidence, but factual accuracy still requires reviewing the sources.

## Checks

```bash
python -m unittest discover -v
python scripts/check_secrets.py
```

The tests mock providers and include a Streamlit UI regression check. GitHub
Actions runs the tests and credential scan. No live API calls are needed.

Keep `.env` local. Only `.env.example` belongs in Git. The credential scanner
is a pattern-based check, not a full audit of repository history. The app sends
queries to You.com and evidence to OpenRouter; it has no database, email
delivery, or business-action integrations.
