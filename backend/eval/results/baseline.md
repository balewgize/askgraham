# askgraham — Phase 7 eval baseline

_Generated 2026-10-13T13:51:38Z · commit `65942b1` · `backend/eval/datasets/qa.jsonl` (sha256:00ef0b17606b, 40 cases)._

Retrieval is measured at the **essay** level, the unit a reader (and the ⌘K palette) cares about: recall@k is success@k for a single gold essay, MRR is the rank of the gold essay, and nDCG@k is its discounted gain. Paragraph recall@k is stricter — the fraction of the hand-labelled gold paragraphs actually covered by a retrieved chunk.

## Configuration

| setting | value |
|---|---|
| cutoff k | 10 |
| primary variant | hybrid · rerank=True |
| generation model | `deepseek/deepseek-v4.1-flash` |
| judge model | `deepseek/deepseek-v4.1-flash` |
| temperature / seed | 0.0 / 7 |
| RRF k / title boost | 60 / 3.0 |
| embedding | `BAAI/bge-small-en-v1.5` (384-dim) |
| chunk max / overlap | 384 / 64 tokens |

## Retrieval ablation (before → after)

| variant | recall@10 | MRR | nDCG@10 | paragraph recall@10 |
|---|---|---|---|---|
| hybrid (rerank off) | 1.000 | 0.845 | 0.884 | 0.900 (10) |
| hybrid (rerank on) | 1.000 | 0.857 | 0.893 | 0.900 (10) |
| vector only | 0.975 | 0.772 | 0.823 | 0.700 (10) |
| lexical only | 0.875 | 0.728 | 0.765 | 0.800 (10) |

- **Reranker:** MRR +0.013, nDCG@10 +0.010.
- **Hybrid vs vector-only:** MRR +0.072, nDCG@10 +0.061.
- **Hybrid vs lexical-only:** MRR +0.117, nDCG@10 +0.118.

### Retrieval by group — hybrid (rerank on)

| group | n | recall@10 | MRR | nDCG@10 |
|---|---|---|---|---|
| concept | 9 | 1.000 | 0.944 | 0.959 |
| entity | 2 | 1.000 | 1.000 | 1.000 |
| paraphrase | 21 | 1.000 | 0.775 | 0.832 |
| title | 8 | 1.000 | 0.938 | 0.954 |

### Retrieval failures — hybrid (rerank on)

Every gold essay was retrieved in the top 10.

## Answer quality

| metric | value (0-1) |
|---|---|
| faithfulness (LLM judge) | 0.956 |
| relevance (LLM judge) | 1.000 |
| citation correctness (LLM judge) | 1.000 |
| quote grounding (verbatim) | 0.924 |
| citation precision (verbatim) | 0.995 |
| answers judged | 40 |
| quoted spans grounded | 121/131 |
| citations valid | 194/195 |
| judge failures | 0 |

Faithfulness, relevance and citation correctness are 1-5 judge scores normalized to 0-1, averaged per metric over the cases where that judge returned a score. Quote grounding splits each quoted span on elisions and inline citation tokens and requires every fragment to appear verbatim in the retrieved sources; citation precision checks each `[slug#start-end]` token against the sources the model was given. Both are exact and cost nothing to run.

### Per-case answers

| id | faith | rel | cite | quotes | citations | answer (excerpt) |
|---|---|---|---|---|---|---|
| do-things-title | 5 | 5 | 5 | 4/4 | 6/6 | "Do things that don't scale" is one of the most common types of advice Y… |
| do-things-why | 5 | 5 | 5 | 1/1 | 5/5 | A startup should do things that don't scale because startups usually don't take… |
| ramen-profitable | 5 | 5 | 5 | 1/1 | 4/4 | Ramen profitable means a startup makes just enough to pay the founders' living… |
| makers-schedule | 5 | 5 | 5 | 18/18 | 6/6 | Graham splits time-use into two types. The manager's schedule is "for bosses,"… |
| schlep-blindness | 4 | 5 | 5 | 1/4 | 5/5 | Schlep blindness is the phenomenon where people—especially hackers and… |
| startup-ideas | 5 | 5 | 5 | 3/7 | 7/7 | The best method is not to try to think up ideas at all. Ask yourself "what do… |
| new-ideas | 5 | 5 | 5 | 0/0 | 7/7 | You get new ideas by noticing anomalies: what seems strange, missing, or… |
| nerds-unpopular | 5 | 5 | 5 | 5/5 | 6/6 | Graham's main answer is that nerds are unpopular because they're distracted:… |
| great-work | 5 | 5 | 5 | 0/0 | 8/8 | Choose work you have a natural aptitude for and a deep interest in… |
| good-writing | 5 | 5 | 5 | 12/12 | 7/7 | Graham's central claim is that writing can be good in two senses — it can sound… |
| disagree-hierarchy | 4 | 5 | 5 | 2/2 | 7/7 | The disagreement hierarchy runs from DH0 to DH6, naming the intermediate stages… |
| startups-america | 5 | 5 | 5 | 0/0 | 8/8 | Graham’s framing is that startups happen in clusters, and the US is a… |
| default-alive | 4 | 5 | 5 | 2/2 | 3/3 | “Default alive or default dead” is the question Graham asks a startup that’s… |
| fatal-pinch | 5 | 5 | 5 | 2/2 | 4/4 | The fatal pinch is the situation many startups reach a few months before they… |
| ambitious-ideas | 5 | 5 | 5 | 6/6 | 3/3 | Frighteningly ambitious startup ideas are the biggest startup ideas, and their… |
| startup-hub | 5 | 5 | 5 | 0/1 | 4/4 | Graham frames the question as the wrong one. Asking whether founders "need" to… |
| present-investors | 5 | 5 | 5 | 3/3 | 4/4 | Focus on two goals: explain what you're doing, and explain why users will want… |
| equity-equation | 5 | 5 | 5 | 1/1 | 4/4 | Use the equity equation. For an employee, if `i` is the average outcome with… |
| founder-mode | 5 | 5 | 5 | 2/2 | 3/3 | Graham's answer is that founder mode is one of two different ways to run a… |
| determination | 5 | 5 | 5 | 9/9 | 5/5 | The sources don't offer a full theory of what makes founders determined, but… |
| think-yourself | 4 | 5 | 5 | 1/1 | 6/6 | You can make yourself more independent-minded; it may be largely inborn, but… |
| good-taste | 5 | 5 | 5 | 0/0 | 5/5 | Good taste is not merely personal preference. In the narrow sense it refers to… |
| write-simply | 5 | 5 | 5 | 3/3 | 6/6 | The core move is to write in spoken language. Read each essay out loud before… |
| top-idea | 5 | 5 | 5 | 10/10 | 5/5 | You can't control it directly — only indirectly. Graham says that barring… |
| bus-ticket-genius | 5 | 5 | 5 | 2/2 | 5/5 | The bus ticket theory of genius says that in addition to natural ability and… |
| safe-nice | 5 | 5 | 5 | 1/1 | 2/2 | It’s safe because making great things is compounded, and rapacity isn’t… |
| lesson-unlearn | 5 | 5 | 5 | 2/2 | 3/3 | The lesson to unlearn is the one schools train you in: winning by hacking the… |
| earn-billion | 5 | 5 | 5 | 8/8 | 5/5 | The most common route: "Starting a successful startup is the most common way to… |
| brand-age | 5 | 5 | 5 | 2/3 | 6/7 | The brand age is the present era of mechanical watchmaking, which began in 1985… |
| superlinear | 5 | 5 | 5 | 1/1 | 4/4 | Superlinear returns are the degree to which returns for performance are not… |
| resourceful | 4 | 5 | 5 | 2/2 | 4/4 | Being relentlessly resourceful is Graham's two-word answer to what makes a good… |
| python-paradox | 5 | 5 | 5 | 0/0 | 1/1 | The Python paradox is Graham’s claim that if a company chooses to write its… |
| beating-averages | 5 | 5 | 5 | 7/8 | 3/3 | Viaweb chose Lisp mainly because rapid development mattered in their market,… |
| microsoft-dead | 5 | 5 | 5 | 2/2 | 5/5 | Graham doesn’t mean Microsoft went bankrupt; he means it stopped being… |
| lose-time-money | 5 | 5 | 5 | 0/0 | 2/2 | You lose money mainly through bad investments, not excessive expenditure.… |
| identity-small | 5 | 5 | 5 | 0/0 | 2/2 | You should keep your identity small because identity blocks clear thinking. A… |
| not-not-startup | 4 | 5 | 5 | 0/0 | 8/8 | Because many of the standard reasons for not starting a startup don’t hold up.… |
| expert-changing | 5 | 5 | 5 | 4/4 | 5/5 | The core problem is that expertise itself goes stale: "When experts are wrong,… |
| hacker-news | 5 | 5 | 5 | 2/2 | 5/5 | Graham says he doesn’t regret that Hacker News grew bigger and took more time… |
| do-what-you-love | 4 | 5 | 5 | 2/2 | 6/6 | Doing what you love is complicated, and it isn't enough just to be told to do… |

## Phase 8: tuning inputs

This file is the **before** column. Phase 8 sweeps these against it and appends the after:

- chunk size {512, 1024, 2048} and overlap
- RRF k and the title boost (unmeasured here — the setting is shared)
- reranker on/off and `RERANK_CANDIDATES` (priced in the table above)
- query rewriting on/off for follow-ups
