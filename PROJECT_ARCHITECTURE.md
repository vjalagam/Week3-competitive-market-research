# Market Signal

## Project Architecture and Technical Design

**Document purpose:** provide a readable technical overview for project review,
handoff, and future maintenance.

Market Signal is a report-only competitive research application. A user enters
a company in Streamlit; the workflow finds up to three competitors, gathers
fresh web and news evidence, asks an OpenRouter-hosted open model to structure
that evidence, validates the result, and renders the reports as cards.

The system intentionally stops at research output. It does not send emails,
write to a database, or take actions on behalf of the user.

### Design Goals

- Keep the user workflow short: one company input and one research action.
- Keep research evidence fresh by querying You.com at run time.
- Keep model output predictable with a fixed JSON shape and Pydantic validation.
- Keep orchestration explicit so each competitor can be traced through the run.
- Keep model cost at zero by using OpenRouter's `openrouter/free` router.

### Technology Stack

| Layer | Technology | Why it is used |
| --- | --- | --- |
| User interface | Streamlit | Input, progress, and report cards |
| Orchestration | LangGraph | State-based workflow with a visible queue loop |
| Search | You.com Search API | Fresh web and recent-news evidence |
| Language model | OpenRouter free router | Routes to available open models at no model cost |
| Validation | Pydantic | Normalizes and validates structured model responses |
| Runtime | Python virtual environment | Keeps dependencies isolated |

## The Shape of the System

This is a hand-drawn-style service architecture: the Streamlit interface feeds
the LangGraph orchestrator, which branches into discovery, research, and
analysis. The green lane is the You.com tool/API boundary; the orange lane is
the structured report returned to Streamlit.

![Market Signal hand-drawn architecture flow](architecture-flow.svg)

```text
   . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .
 .   INGESTION - FRESH SIGNALS ARRIVE WHEN A RESEARCH RUN STARTS          .
 .                                                                       .
 .  [ COMPANY NAME ] --> [ You.com competitor evidence ] --> [ web/news ] .
 .                                                                       .
   . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .
                                                   |
                                                   v
                                     +---------------------+
                                     |    USER QUESTION     |
                                     |  company to research |
                                     +----------+----------+
                                                      |
                                                      v
                                     +---------------------+
                                     | 1  DISCOVER          |
                                     | LangGraph + You.com  |
                                     | find up to 3 names   |
                                     +----------+----------+
                                                      |
                                                      v
                                     +---------------------+
                                     | 2  RESEARCHER        |
                                     | web search + news    |
                                     | concurrent evidence |
                                     +----------+----------+
                                                      |
                                                      v
                                     +---------------------+
                                     | 3  ANALYST           |
                                     | OpenRouter free      |
                                     | model returns JSON  |
                                     +----------+----------+
                                                      |
                                                      v
                                     +---------------------+
                                     | 4  VALIDATOR         |
                                     | Pydantic normalizes  |
                                     | CompetitorReport    |
                                     +----------+----------+
                                                      |
                                                      v
                                     +---------------------+
                                     | 5  REPORT CARD       |
                                     | Streamlit renders    |
                                     | answer + sources    |
                                     +---------------------+
                                                      |
                                                      v
                                     +---------------------+
                                     | COMPETITIVE SNAPSHOT|
                                     | pricing | features  |
                                     | news | strengths    |
                                     +---------------------+

          . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .
         . RETRY SEARCH .                 . REGENERATE / PROVIDER RETRY     .
         . 2 -> You.com                   . 3 -> OpenRouter free router     .
          . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .

                         queue still has competitors?  yes -> step 2
                         no -> step 5 -> final report cards
```

   ### Updated Runtime Flow

   ```text
   1. User enters company
          |
          v
   2. Streamlit checks input and API keys
          |
          v
   3. discover: You.com competitor evidence
          |
          v
   4. discover: free OpenRouter model extracts up to 3 names
          |
          v
   5. queue router -- competitor remains? -- yes --> researcher
          |                                           |
          |                                           +--> web search
          |                                           +--> news search (fresh)
          |                                           |
          |                                           v
          |                                      analyst
          |                                           |
          |                                           +--> free model returns JSON
          |                                           +--> Pydantic validates report
          |                                           |
          |                                           +--> loop to queue router
          |
          +-- no --> END --> Streamlit renders report cards

   Any API, provider, parsing, or validation failure
          |
          v
   Streamlit status becomes "Research failed" and shows an actionable error
   ```

## Request Walkthrough

1. `app.py` loads `.env`, collects the company name, and checks that both API
   keys are present. The model is configured with `OPENROUTER_MODEL`, currently
   set to `openrouter/free`.
2. `CompetitiveResearchPipeline` starts the LangGraph state machine with an
   empty competitor queue and report list.
3. The `discover` node asks You.com for competitor evidence. The analyst sends
   that evidence to the OpenRouter free router, which selects an available free
   open model to extract up to three competitor names.
4. The queue router sends one competitor at a time to `researcher`.
5. `YouComClient.parallel_research` runs two searches concurrently:
   - web: pricing, features, product, and positioning
   - news: recent announcements, funding, and product updates
6. `analyst` gives the evidence to OpenRouter and parses the JSON response into
   a `CompetitorReport` using Pydantic validation. Text and list fields are
   normalized when a model returns a nested object or string instead of the
   preferred shape.
7. If competitors remain, the graph loops back to `researcher`. Otherwise it
   ends and Streamlit renders the reports.

## Main Components

| Component | Responsibility |
| --- | --- |
| `app.py` | Streamlit page, credentials check, progress state, and report cards |
| `pipeline.py` | LangGraph nodes, state transitions, and competitor queue |
| `youcom_client.py` | You.com Search API adapter and parallel web/news research |
| `analyst.py` | OpenRouter prompts, JSON extraction, and report generation |
| `models.py` | Search result and report schemas plus response normalization |
| `.env` | Local API credentials and model configuration; never commit it |
| `test_pipeline.py` | Offline graph smoke test using local fake clients |

## State Passing Through the Graph

```text
ResearchState
  company            "Figma"
  competitor_queue   ["Canva", "Miro", "..." ]
  current_competitor "Canva"
  search_results     { web: [...], news: [...] }
  reports            [ CompetitorReport, ... ]
  status             "Researched Canva"
  error              null
```

The queue is the small piece that makes the workflow repeatable: each research
and analysis pass removes one competitor, appends one report, and either loops
or finishes. Web and news searches for a single competitor run concurrently,
while competitor reports are generated one at a time through the graph queue.

## External Boundaries

```text
Browser
  |
  | HTTP
  v
Streamlit (localhost:8501)
  |                         \
  | X-API-Key                \ Authorization: Bearer
  v                           v
You.com Search API          OpenRouter API
  |                           |
   +-------- search evidence -+----> openrouter/free --> LLM JSON --> Pydantic report
```

The model is configured through `OPENROUTER_MODEL`. `openrouter/free` is
preferred over a pinned free provider because provider availability and rate
limits can change. A free route can still be temporarily unavailable; that is
an external capacity limitation, not a change to the application workflow.

## Security and Operational Notes

- `.env` is ignored by Git and must remain local. Never place API keys in source
   files or project documentation.
- The You.com key is sent only as the `X-API-Key` request header.
- The OpenRouter key is sent only as a bearer token to the OpenRouter endpoint.
- Search results and reports are held in Streamlit session state and are not
   written to a database by this project.
- Live runs require network access, valid API keys, and available provider
   capacity. The smoke test does not require network access.

## Failure Boundaries

| Boundary | Typical problem | User-visible behavior |
| --- | --- | --- |
| Input | Empty company name | Streamlit asks for a company name |
| Credentials | Missing key | Streamlit asks for `.env` values |
| You.com | 401/403 or network failure | Pipeline stops and shows the API error |
| OpenRouter | 429 provider limit or no credits | Pipeline stops and shows the model/provider error |
| Model output | Invalid or non-JSON response | Report parsing fails and Streamlit shows the exception |
| Validation | Missing or malformed report fields | Pydantic rejects the report and Streamlit shows the exception |

## Running the Project

```bash
source .venv/bin/activate
streamlit run app.py
```

For a network-free check of the graph behavior:

```bash
python test_pipeline.py
```

## Suggested Future Improvements

1. Add bounded retries with short backoff for transient 429 and 5xx responses.
2. Add a model fallback list when the free router has no available provider.
3. Add structured logging with request IDs, without logging API keys or full
   evidence payloads.
4. Add tests for malformed model JSON, empty competitor discovery, and API
   authorization failures.
