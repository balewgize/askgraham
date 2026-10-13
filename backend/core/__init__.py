"""Cross-cutting infrastructure: database, ORM metadata, logging, domain errors.

Dependency rule — `core` sits below everything except `config`. Nothing in this
package may import from `main`, `cli`, `rag`, or `llm`. That one constraint is
what keeps the graph acyclic:

    main · cli  →  rag · llm  →  core  →  config

Modules here are deliberately free of domain knowledge: they know how to talk to
Postgres and how to log, not what an essay or a citation is.
"""
