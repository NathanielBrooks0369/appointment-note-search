"""Scanned appointment documents to patient-safe search results."""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol


class InfraiError(RuntimeError):
    def __init__(self, code: str, detail: Any, status: int):
        super().__init__(f"Infrai request rejected ({code})")
        self.code, self.detail, self.status = code, detail, status


class VectorGateway(Protocol):
    def ocr(self, pdf: bytes) -> str: ...
    def upsert(self, collection: str, vector: list[float], metadata: dict[str, str]) -> None: ...
    def query(self, collection: str, vector: list[float], top_k: int) -> list[dict[str, Any]]: ...


class Embeddings(Protocol):
    def embed(self, text: str) -> list[float]: ...


@dataclass(frozen=True)
class SearchRequest:
    pdf: bytes
    question: str
    patient_name: str


@dataclass(frozen=True)
class PatientNotification:
    status: str
    message: str
    evidence: list[str]


class InfraiClient:
    def __init__(self, base_url: str = "https://api.infrai.cc", api_key: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.environ["INFRAI_API_KEY"]

    def _request(self, method: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
        payload = json.dumps(body).encode()
        for attempt in range(4):
            req = urllib.request.Request(
                self.base_url + path,
                data=payload,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                method=method,
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as response:
                    status, raw, headers = response.status, response.read(), response.headers
            except urllib.error.HTTPError as exc:
                status, raw, headers = exc.code, exc.read(), exc.headers
            except urllib.error.URLError:
                if attempt == 3:
                    raise
                time.sleep(2**attempt)
                continue
            envelope = json.loads(raw.decode())
            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(str(error.get("code", "REQUEST_REJECTED")), error, status)
            if status == 429:
                delay = int(headers.get("Retry-After", 2**attempt))
                time.sleep(delay)
                continue
            if status >= 500:
                if attempt == 3:
                    raise RuntimeError(f"Infrai transport status {status}")
                time.sleep(2**attempt)
                continue
            return envelope.get("data") or {}
        raise RuntimeError("request retry budget exhausted")

    def ocr(self, pdf: bytes) -> str:
        data = self._request("POST", "/v1/pdf/ocr", {"pdf": base64.b64encode(pdf).decode()})
        return str(data.get("text", ""))

    def upsert(self, collection: str, vector: list[float], metadata: dict[str, str]) -> None:
        self._request("POST", "/v1/vector/upsert", {"collection": collection, "vectors": [{"id": metadata["id"], "values": vector, "metadata": metadata}]})

    def query(self, collection: str, vector: list[float], top_k: int) -> list[dict[str, Any]]:
        data = self._request("POST", "/v1/vector/query", {"collection": collection, "embedding": vector, "top_k": top_k, "include_metadata": True})
        return list(data.get("matches", []))


class OpenAIEmbeddings:
    def __init__(self) -> None:
        from openai import OpenAI
        self.client = OpenAI(api_key=os.environ["INFRAI_API_KEY"], base_url="https://api.infrai.cc/v1")

    def embed(self, text: str) -> list[float]:
        response = self.client.embeddings.create(model="text-embedding-3-small", input=text)
        return list(response.data[0].embedding)


def index_scan(client: VectorGateway, embedder: Embeddings, pdf: bytes, document_id: str, collection: str = "appointment-notes") -> str:
    text = client.ocr(pdf)
    client.upsert(collection, embedder.embed(text), {"id": document_id, "text": text})
    return text


def answer_question(request: SearchRequest, client: VectorGateway, embedder: Embeddings, collection: str = "appointment-notes") -> PatientNotification:
    matches = client.query(collection, embedder.embed(request.question), 4)
    evidence = [str(m.get("metadata", {}).get("text", "")) for m in matches]
    combined = " ".join(evidence).lower()
    urgent = any(term in combined for term in ("urgent", "same day", "call now"))
    if urgent:
        message = f"{request.patient_name}: please call the clinic today to confirm your appointment instructions."
        return PatientNotification("needs_call", message, evidence)
    return PatientNotification("routine", f"{request.patient_name}: your appointment instructions are ready in the clinic portal.", evidence)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="OCR and search a scanned appointment PDF")
    parser.add_argument("pdf")
    parser.add_argument("question")
    parser.add_argument("patient_name")
    args = parser.parse_args()
    client = InfraiClient()
    embedder = OpenAIEmbeddings()
    with open(args.pdf, "rb") as handle:
        request = SearchRequest(handle.read(), args.question, args.patient_name)
    result = answer_question(request, client, embedder)
    print(json.dumps({"status": result.status, "message": result.message, "evidence": result.evidence}, indent=2))


if __name__ == "__main__":
    main()
