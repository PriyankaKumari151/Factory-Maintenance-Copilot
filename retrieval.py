"""Two explicitly labelled retrieval modes; no silent semantic-to-keyword fallback."""
import os
from pathlib import Path
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from config import DATA


class SOPRetriever:
    def __init__(self, backend=None):
        self.backend = backend or os.getenv('RETRIEVAL_BACKEND', 'tfidf')
        self.chunks = []
        for path in sorted((DATA / 'sops').glob('*.md')):
            metadata_text, body = path.read_text(encoding='utf-8').split('\n---\n', 1)
            metadata = dict(line.split(': ', 1) for line in metadata_text.strip().splitlines())
            # A whole heading section is the chunk; each synthetic SOP has two sections.
            for section in body.split('## ')[1:]:
                heading, content = section.split('\n', 1)
                self.chunks.append({**metadata, 'section': heading.strip(), 'text': content.strip(),
                                    'source': f"{metadata['document_id']} v{metadata['version']} / {heading.strip()}"})
        if not self.chunks:
            raise ValueError('No SOP documents found in data/sops.')
        texts = [f"{c['title']} {c['machine_type']} {c['fault_code']} {c['section']} {c['text']}" for c in self.chunks]
        if self.backend == 'tfidf':
            self.vectorizer = TfidfVectorizer()
            self.matrix = self.vectorizer.fit_transform(texts).toarray()
        elif self.backend == 'semantic':
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(os.getenv('EMBEDDING_MODEL', 'sentence-transformers/all-MiniLM-L6-v2'))
            self.matrix = self.model.encode(texts, normalize_embeddings=True)
        else:
            raise ValueError('RETRIEVAL_BACKEND must be tfidf or semantic.')

    def retrieve(self, question, machine_type=None, fault_code=None, k=3):
        if self.backend == 'tfidf':
            vector = self.vectorizer.transform([question]).toarray()[0]
        else:
            vector = self.model.encode([question], normalize_embeddings=True)[0]
        scores = self.matrix @ vector  # L2-normalised vectors: dot product = cosine similarity.
        candidates = [i for i, c in enumerate(self.chunks)
                      if (not machine_type or c['machine_type'] == machine_type)
                      and (not fault_code or c['fault_code'] == fault_code)]
        ordered = sorted(candidates, key=lambda i: float(scores[i]), reverse=True)[:k]
        return [{**self.chunks[i], 'score': round(float(scores[i]), 4)} for i in ordered if scores[i] > 0]
