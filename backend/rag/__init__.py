"""Corpus pipeline: get the essays in, get them indexed, get them back out.

Owns `ingest` (content JSON → Postgres), `chunking`, `embeddings`, `retrieval`
and `snapshot` (Postgres → frontend JSON). May import `core` and `config`; must
not import `main` or `cli`, which are its callers.
"""
