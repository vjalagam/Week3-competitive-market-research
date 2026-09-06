# Market Signal

A report-only competitive market research pipeline built with LangGraph, OpenRouter, You.com Search API, and Streamlit.

## What it does

1. Accepts a company name in Streamlit.
2. Uses You.com web search to discover the top three competitors.
3. Runs web and news research in parallel for each competitor.
4. Uses an OpenRouter-hosted model with a compact ReAct-style analyst prompt to structure evidence into JSON reports.
5. Stops after rendering interactive competitor cards.

It does not send email, write to a database, or take business actions.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Add OPENROUTER_API_KEY and YDC_API_KEY to .env
streamlit run app.py
```

Run the offline graph smoke test with:

```bash
python test_pipeline.py
```

The You.com adapter uses `POST https://ydc-index.io/v1/search` with the `X-API-Key` header. The key must be a You.com Search API key, not an OpenRouter or regular You.com account key.
