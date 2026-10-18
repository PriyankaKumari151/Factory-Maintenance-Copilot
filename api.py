"""FastAPI application: input validation and one cached set of components per process."""
import logging
from datetime import date
from functools import lru_cache
from time import perf_counter
from typing import Literal
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, model_validator
from database import machines
from retrieval import SOPRetriever
from platform_client import InventoryClient
from llm_client import GeminiClient
from workflow import build_workflow

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
app = FastAPI(title='Factory Maintenance Copilot', version='0.1.0')


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    intent: Literal['sop', 'analytics', 'combined'] = 'combined'
    start_date: date = date(2026, 10, 1)
    end_date: date = date(2026, 10, 7)
    machine_id: str | None = Field(default=None, pattern=r'^M00[1-3]$')
    fault_code: str | None = None

    @model_validator(mode='after')
    def valid_dates(self):
        if self.end_date < self.start_date:
            raise ValueError('End date precedes start date')
        return self


class AskResponse(BaseModel):
    question: str
    answer: dict
    evidence: dict
    trace: list[str]
    retrieval_backend: str
    elapsed_seconds: float


@lru_cache(maxsize=1)
def components():
    retriever = SOPRetriever()
    return retriever, build_workflow(retriever, InventoryClient(), GeminiClient())


@app.get('/health')
def health():
    return {'status': 'ok', 'dataset': 'synthetic'}


@app.get('/machines')
def list_machines():
    return machines()


@app.post('/ask', response_model=AskResponse)
def ask(request: AskRequest):
    before = perf_counter()
    try:
        retriever, graph = components()
        result = graph.invoke(request.model_dump(mode='json'))
    except Exception as exc:
        # Log error TYPE only; avoid provider URLs / secrets / raw user documents in logs.
        logger.error('Workflow failed: %s', type(exc).__name__)
        raise HTTPException(503, 'Workflow unavailable. Check database setup and retrieval configuration.') from None
    elapsed = round(perf_counter() - before, 3)
    logger.info('intent=%s elapsed_seconds=%s', request.intent, elapsed)
    return {'question': request.question, 'answer': result['answer'], 'evidence': result['evidence'],
            'trace': result['trace'], 'retrieval_backend': retriever.backend, 'elapsed_seconds': elapsed}
