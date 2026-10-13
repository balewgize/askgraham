7-day plan: AI engineering through the PG essay reader

The idea: build one real AI product instead of doing seven tutorials, learning each layer as you hit it. The PG reader works because it’s a real RAG problem with a public demo.

Day 1: First working call

Get a model API running from your backend, with streaming and a system prompt
Build “chat about this essay” by pasting one essay into context
Output: working single-essay chat

Day 2: Structured output

Make the model return JSON with a schema (Pydantic or Zod)
Batch-generate summaries: thesis, non-obvious ideas, key quotes
Check that every quote exists verbatim in the source
Output: summaries for 20 essays

Day 3: Retrieval (RAG)

Chunk the essays, create embeddings, store them in pgvector or SQLite
Retrieve top-k chunks across the whole catalog
Answer with citations to the essay and paragraph
Output: “Ask PG anything” with sources

Day 4: Evals (the most important day)

Write 30 test questions with known answers
Score retrieval (did the right chunk come back?) and answers (LLM-as-judge plus manual checks)
Save the baseline numbers
Output: an evals/ folder with a script and results table

Day 5: Improve using the evals

Try 3 changes: chunk size, hybrid keyword and vector search, reranking or query rewriting
Re-run the evals after each change and keep what wins
Track cost and latency per query
Output: a before/after table, your best portfolio asset

Day 6: Tools and product polish

Add one tool, like “find related essays” or “compare what PG says about X across essays”
Build the UI properly: streaming, clickable citations, loading and error states
Add logging and rate limiting
Output: a shippable interface

Day 7: Ship and show

Deploy publicly
Write a post: what you built, what failed, the eval numbers, what’s next
Clean up the README with a demo GIF and architecture diagram
Share it, and DM 10 founders or teams with the link
Output: live demo, repo, write-up, 10 outreach messages