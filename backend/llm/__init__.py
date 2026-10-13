"""Model-facing layer: the OpenRouter client, chat generation, batch summaries.

Split from `rag` on purpose. Embeddings are local ONNX — free, offline,
reproducible. Everything here talks to a remote API: it costs money, needs a
network, and fails differently. Keeping them apart makes the cost and failure
boundary visible in the directory tree rather than buried in import graphs.

May import `core` and `config`; must not import `main` or `cli`.
"""
