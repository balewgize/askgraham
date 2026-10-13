"""Eval harness: retrieval and answer-quality measurement.

Deliberately depends on `rag` and `llm` as a *consumer*, never the reverse. It
is the thing that tells you whether a change to the pipeline actually helped,
which is why it imports both but neither imports it.
"""
