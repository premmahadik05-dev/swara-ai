# data/test/

Held-out test set for one question: *can a customer order an imported, branded product by saying its name?*

| File | What it is |
|---|---|
| `branded_utterances.jsonl` | 300 sentences, one JSON object per line: `id`, `text`, `lang` (gu, hi, en, hinglish), `expect_ean`, `expect_name`, `provenance` = `synthetic` (the sentence), `product_provenance` = `sourced` (the product) |
| `branded_results.json` | Output of `python scripts/evaluate_branded.py`: verdict counts, per-language counts, sample misses, caveats |

**How it is built.** `scripts/data/make_test_set.py` takes products only from the catalogue's `test` split (a random 10%, 527 products) and fills fixed templates such as "bhaiya 2 {name} chahiye" in four languages. Products from the `train` split are never used here, so matching rules can be tuned on `train` without touching this file.

**What it can and cannot tell you.**

- The sentences are templated from the product's own name, so this is an **optimistic ceiling** for name recognition, not a measure of real customers.
- It is **text only**. No speech recognition is involved; Gnani Prisma may mis-hear brand names (use the Noise lab for that).
- The split is random within one crowdsourced catalogue, so brands and naming patterns are shared between `train` and `test`.
- Only the 527 held-out products are imported for the run, so there are fewer look-alike competitors than in a full shop. With the whole catalogue imported, the 288-sentence staples gold set (`eval/`) is unchanged: a test in `backend/tests/test_branded_nlu.py` checks that no gold utterance changes its result.
