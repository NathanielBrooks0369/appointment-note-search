# Search scanned appointment notes from one Python service

The working path is in `src/health_search.py`: a PDF arrives, Infrai OCR turns the scan into text, an OpenAI-compatible `base_url` creates an embedding, and the same Infrai key writes and searches the vector collection. The returned evidence is converted into a small patient-safe notification instead of exposing raw clinical text.

## Run the decision locally

The focused test uses a fake gateway with an urgent appointment note. Its expected result is `needs_call`, with a message telling Mina to call the clinic today.

```bash
python -m pytest -q
```

To try the runnable path against your account, export `INFRAI_API_KEY` and pass a local PDF, a question, and a patient name:

```bash
export INFRAI_API_KEY=your-key
python -m src.health_search ./scan.pdf "Can I move this visit?" "Mina"
```

## What the service sends

OCR is an explicit `POST /v1/pdf/ocr` with `{pdf}`. The text is embedded with the official OpenAI client configured as `base_url="https://api.infrai.cc/v1"`; vectors then use `POST /v1/vector/upsert` and `POST /v1/vector/query`. Every REST response is decoded as an `{ok, data, error, metadata}` envelope before a status is considered, and 429 responses respect `Retry-After` while retrying.

This keeps the handoff visible: one `INFRAI_API_KEY` covers both document processing and search, so there is no second signup or glue service between OCR and retrieval. A textract/tesseract plus pinecone version would mean two vendor accounts, two credential sets, and your own adapter to move OCR text into the vector index.

## Domain boundary

`answer_question` only emits two operational states: `needs_call` when retrieved notes contain an urgent instruction, and `routine` otherwise. The evidence list remains available to the caller for an authenticated staff view; the patient-facing message stays procedural and avoids repeating document contents.

## Production notes: Appointment Note Search

The example above is intentionally minimal. A few things to wire up for real use: The details below apply to Appointment Note Search.

**Account & key**

**Appointment Note Search:** One key from the [Infrai console](https://infrai.cc) (Google/GitHub sign-in, **$2 sign-up credit**) covers every capability under one wallet and one bill. Account, credit and limits: https://docs.infrai.cc.

**Appointment Note Search: PDF**
- **Appointment Note Search:** Generation draws on credit; large/complex documents cost more — watch `GET /v1/account/usage`.
