# Gemma evaluation records

2026-10-17 board HTTP evaluation. These are results for **the previous prompt/schema that used portion/clarify**, not a re-evaluation against the current intent/item/not_understood contract.

| Model | Original 20 | Synthetic distorted 20 | Median HTTP time (original / distorted) |
| --- | --- | --- | --- |
| Gemma4 | 16/20 | 15/20 | 1.975 s / 1.781 s |
| Gemma3 | 0/20 | 0/20 | See raw record |

Gemma3 failed output contract validation on all 40, and 34 of them returned the user input JSON unchanged. The Markdown fence itself was not the main cause of failure. This observation alone does not establish whether the model or the serving template is the cause. The default board model and automatic evaluation use Gemma4; the code for explicitly running Gemma3 remains.

- [Full prompt and per-case input/output/time](drinks-20261017T230141554405Z.md)
- [Raw HTTP responses, stats, request JSON](drinks-20261017T230141554405Z.json)
- Current evaluation sets: [original 20](../../fixtures/drink_cases.json), [synthetic distorted 20](../../fixtures/drink_cases_distorted.json)
- Rerun: [`evaluate_gemma.py`](../../scripts/evaluate_gemma.py); the default URL is the PC tunnel `127.0.0.1:18000`, and the default model is Gemma4.

At that time, calls went sequentially PC → SSH tunnel → board localhost:8000. This is not a real audio/image evaluation, and the distorted sentences are synthetic text. The expected values and requests of earlier results are kept in the raw files and may differ from the current fixtures. New evaluations also save input/output/time to new JSON and Markdown files.
