# Statistics

Figures about the daily runs, newest first. Model costs come from the `model_calls` table in `data/local.db`.

## Model cost by part, 2026-10-29 to 11-02 (written 2026-11-02)

Without the duo script, which is left out of the daily run from 2026-11-03 (`69233dd`), the last five runs cost
**$4.59** in all: **$0.92 a run** on average, from $1.34 on a busy weekday to $0.45 on a quiet Monday. The editor and
the podcast writer take about 70% of it.

| Part (step) | 10-29 | 10-30 | 10-31 | 11-01 | 11-02 | 5 days | Share |
|---|---|---|---|---|---|---|---|
| **Editor** (step 5) | $0.51 | $0.32 | $0.35 | $0.24 | $0.17 | **$1.60** | 35% |
|  · rating the candidates | 0.31 | 0.18 | 0.20 | 0.13 | 0.08 | 0.90 | |
|  · recovery pass | 0.11 | 0.07 | 0.07 | 0.05 | 0.04 | 0.34 | |
|  · final list + lighter side | 0.09 | 0.07 | 0.08 | 0.06 | 0.05 | 0.36 | |
| **Podcast writer** (step 8) | $0.41 | $0.37 | $0.34 | $0.26 | $0.17 | **$1.54** | 34% |
| **Briefing writer** (stories + links, step 8) | $0.28 | $0.22 | $0.19 | $0.13 | $0.09 | **$0.91** | 20% |
| **Grouping judge** (step 4) | $0.14 | $0.13 | $0.14 | $0.11 | $0.02 | **$0.54** | 12% |
| **Total without duo** | **$1.34** | **$1.05** | **$1.02** | **$0.74** | **$0.45** | **$4.59** | |
| *Duo script (now off)* | *0.40* | *0.35* | *0.32* | *0.27* | *0.17* | *1.50* | |
| *Run total as recorded* | *1.74* | *1.40* | *1.34* | *1.00* | *0.61* | *6.09* | |

- **Cost follows the news.** Every part grows with the number of stories, so cheap weekend runs are thin runs, not
  savings. The 2026-11-02 total leaves out the extra stories and week in review written by hand that day
  (`experiments/weekend_edition`).
- **Rating the candidates** is the largest single item: 2 to 7 requests a run, mostly paid for by the written ratings.
- **The podcast writer** makes about 11 requests a run, each sent the story material again: about 100,000 input
  tokens on a busy day.
- **The grouping judge** makes up to 60 small requests a run (the cap). It cost $0.02 on 2026-11-02, with 8 pairs.

Ways to cut further, not yet tried:

1. Send the judge's pairs in one batched request (about $0.10 a day, low risk).
2. Ask the rater for shorter reasons (about $0.10 to $0.15 on busy days).
3. Reuse the podcast's story material across its segment requests with prompt caching (likely the most, to be measured).

The query behind the table:

```sql
select r.run_date, m.step, m.purpose, count(*), sum(m.tokens_in), sum(m.tokens_out), sum(m.cost)
from runs r join model_calls m on m.run_id = r.id
where r.run_date >= '2026-10-29'
group by r.id, m.step, m.purpose order by r.id, m.step;
```
