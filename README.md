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
# Create .env and add OPENROUTER_API_KEY and YDC_API_KEY.
# Use the free OpenRouter router for model requests:
OPENROUTER_MODEL=openrouter/free
streamlit run app.py
```

## Configure OpenRouter Free Models

The application uses OpenRouter's OpenAI-compatible API through
`langchain-openai`. Set `OPENROUTER_API_KEY` in the local `.env` file, then
use `OPENROUTER_MODEL=openrouter/free`. The free router chooses an available
zero-cost model for each request, so the application does not require
OpenRouter credits for model inference.

Example `.env` configuration:

```dotenv
OPENROUTER_API_KEY=your_openrouter_key
YDC_API_KEY=your_youcom_search_key
OPENROUTER_MODEL=openrouter/free
APP_URL=http://localhost:8501
```

### Getting an OpenRouter Key

1. Create or sign in to an account at [OpenRouter](https://openrouter.ai/).
2. Create an API key in the OpenRouter keys page.
3. Put the key in `.env`; do not commit the file or paste the key into source
	 code.
4. Leave `OPENROUTER_MODEL=openrouter/free` to let OpenRouter select from its
	 currently available free models.

You still need a separate You.com Search API key because search evidence is
provided by You.com, not by the language model. Add it as `YDC_API_KEY`.

### Free Model Notes

- Free models have shared provider capacity and can return HTTP 429 when busy.
- `openrouter/free` can route around an unavailable free provider, but it is
	not a guarantee that every request will be available immediately.
- To pin a specific free model, replace the value with a model ID ending in
	`:free` from the [OpenRouter models catalog](https://openrouter.ai/models).
- Paid model IDs or paid provider routing may require credits even when the
	application code is otherwise configured correctly.
- The app expects JSON from the model. Choose a text-generation model that
	supports instruction following if you pin a model manually.

To test the configured model without running the full search pipeline:

```bash
python -c 'import os, requests; from dotenv import load_dotenv; load_dotenv(); r=requests.post("https://openrouter.ai/api/v1/chat/completions", headers={"Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"], "Content-Type": "application/json"}, json={"model": os.getenv("OPENROUTER_MODEL", "openrouter/free"), "messages":[{"role": "user", "content": "Reply with exactly OK"}], "max_tokens": 5}, timeout=45); print(r.status_code, r.json().get("model"))'
```

If the response is `429`, wait and retry or choose another currently listed
free model. This indicates temporary provider capacity, not a missing Python
dependency.

Run the offline graph smoke test with:

```bash
python test_pipeline.py
```

The You.com adapter uses `POST https://ydc-index.io/v1/search` with the `X-API-Key` header. The key must be a You.com Search API key, not an OpenRouter or regular You.com account key.

## Security Before Pushing to GitHub

Never commit `.env`, API keys, private keys, or copied terminal output. The
repository ignores `.env` and includes `.env.example` as the safe template.
Run the local secret scan before committing:

```bash
python scripts/check_secrets.py
```

GitHub Actions runs the same scan on every push and pull request. If a real key
is ever committed or shared, revoke it immediately in the provider dashboard
and create a replacement. A GitHub repository secret or environment variable
is the right place for credentials used by future deployment workflows.
