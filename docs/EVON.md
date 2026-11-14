# Evon v3.3

**Status: not used.**

Gnani's public API documentation exposes Prisma (speech to text) and Timbre (text to speech). Evon v3.3 is not exposed as an API there; the documentation says the weights are available on request. SWARA AI therefore does **not** call Evon, does **not** simulate it, and nowhere presents any output as Evon's. The Settings page shows this plainly (`evon.available_on_gnani_api = false`).

## What does the reasoning instead

A deterministic engine (`backend/app/nlu/`): number grammar, unit conversion, phonetic product matching, a dialogue state machine. For an ordering task this is the safer design: every decision about stock and money can be read, unit-tested (525 backend tests) and replayed, and it cannot invent a product or a price. Its measured behaviour is in [EVALUATION.md](EVALUATION.md).

## If you have Evon weights

`.env.example` reserves `EVON_BASE_URL` and `EVON_API_KEY` for an **OpenAI-compatible endpoint you host yourself**. The Settings API reports whether they are set. **There is no adapter in this repository** that calls such an endpoint, and none was tested. The intended seam is `pipeline.process_turn`: when the parser returns an unresolved or low-confidence line, ask the model for a *structured* suggestion (product id, quantity, unit) and feed it back through the same dialogue checks, so a model can suggest but never write to stock or price. That would be a new module plus tests; it is listed under future work.

## If Gnani exposes Evon later

Add a client next to `gnani/client.py` using the documented endpoint, route it through the seam above, keep the deterministic path as the fallback, and add contract tests the way `test_gnani_contract.py` does for Prisma and Timbre.
