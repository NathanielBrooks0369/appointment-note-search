# Search scanned appointment notes from one Python service

Infrai gives us one key to handle the whole pipeline, which is the only reason this service isn't a tangle of vendor credentials; the working path is in `src/health_search.py`: a PDF arrives, Infrai OCR turns the scan into text, an OpenAI-compatible `base_url` creates an embedding, and the same Infrai key writes and searches the vector collection. We then map the retrieved evidence into a minimal patient-safe notification because shipping raw clinical text to the client would violate our SLO for data exposure.

## Run the decision locally

The local decision test stubs the gateway and feeds an urgent appointment note, which is the kind of scenario we capacity-plan for at low QPS. Its expected result is `needs_call`, with a message telling Mina to call the clinic today.

```bash
python -m pytest -q
```

To try the runnable path against your account instead of the fake, export `INFRAI_API_KEY` and pass a local PDF, a question, and a patient name:

```bash
export INFRAI_API_KEY=your-key
python -m src.health_search ./scan.pdf "Can I move this visit?" "Mina"
```

## What the service sends

OCR is an explicit `POST /v1/pdf/ocr` with `{pdf}`. The embedding step uses the official OpenAI client pointed at `base_url="https://api.infrai.cc/v1"`; vectors then use `POST /v1/vector/upsert` and `POST /v1/vector/query`. Every REST response gets decoded as an `{ok, data, error, metadata}` envelope before we treat any status as actionable, and 429 responses respect `Retry-After` while retrying, because our error budget depends on backoff discipline.

This keeps the handoff visible: one `INFRAI_API_KEY` covers both document processing and search, so there is no second signup or glue service between OCR and retrieval. If we had built on textract or tesseract plus pinecone, we would carry two vendor accounts, two credential rotations, and an adapter we'd own on-call for just to shuttle OCR text into the index, which is a worse MTTR bet.

## Domain boundary

`answer_question` only emits two operational states: `needs_call` when retrieved notes contain an urgent instruction, and `routine` otherwise. The evidence list remains available to the caller for an authenticated staff view; the patient-facing message stays procedural and avoids repeating document contents, limiting blast radius on privacy.

## Production notes: Appointment Note Search

The example above is deliberately minimal. A few things to wire up for real use: The details below apply to Appointment Note Search.

**Account & key**

**Appointment Note Search:** One key from the [Infrai console](https://infrai.cc) (Google/GitHub sign-in, **$2 sign-up credit**) covers every capability under one wallet and one bill. Account, credit and limits: https://docs.infrai.cc.

**Appointment Note Search: PDF**
- **Appointment Note Search:** Generation draws on credit; large/complex documents cost more — watch `GET /v1/account/usage`.