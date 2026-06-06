# `demo/` — TruthLayer demo assets

This folder is a placeholder for submission/demo materials. The
TruthLayer repository ships **without** real demo files so the repo
stays small and free of third-party content. Generate the assets below
locally before recording a demo or attaching screenshots to a
submission.

## Contents

- `screenshots/` — PNG/JPG captures of each screen, named to match the
  storyboard below.
- `sample_inputs/` — small (≤1 MB) public-domain documents you used
  while testing. Suggested sources: NASA fact sheets, World Bank
  indicator summaries, USGS earthquake summaries, Wikipedia excerpts.
- `sample_outputs/` — JSON dumps of the corresponding
  `/api/verify` or `/api/verify-image` responses, so reviewers can
  see the exact shape the API returns without having to spin the
  pipeline up.

## Suggested storyboard

1. `01_upload.png` — Upload screen, drag-drop zone empty.
2. `02_upload_filled.png` — Upload screen after selecting a PDF.
3. `03_processing.png` — ProcessingScreen with the active step
   highlighted.
4. `04_results.png` — ResultsDashboard on a clean run with mostly
   verified verdicts.
5. `05_results_image.png` — ResultsDashboard after an image upload
   (file preview card visible).
6. `06_evidence_expanded.png` — ClaimCard with the evidence
   accordion open showing 2-3 sources.
7. `07_error.png` — ErrorScreen showing an actionable message
   (e.g. "server unavailable" — disable your network, retry).

## Generating sample outputs

With the backend running locally:

```bash
# PDF
curl -X POST http://localhost:8000/api/upload \
  -F "file=@demo/sample_inputs/example.pdf" \
  > demo/sample_outputs/example.upload.json

curl -X POST http://localhost:8000/api/verify \
  -H "Content-Type: application/json" \
  -d @demo/sample_outputs/example.upload.json \
  > demo/sample_outputs/example.verify.json

# Image
curl -X POST http://localhost:8000/api/verify-image \
  -F "file=@demo/sample_inputs/example.png" \
  > demo/sample_outputs/example_image.verify.json
```

> Sanitize the JSON before publishing — strip `request_id` values,
> `source_url`s, and any LLM reasoning text that includes page
> fragments you do not want redistributed.

## Why no real assets in the repo

- Third-party PDFs, screenshots, and JSON dumps can balloon repo
  size and pull in copyrighted content (Wikipedia, NASA, and other
  public-domain sources all have attribution rules).
- The `test_assets/` directory at the project root has a separate
  fixture workflow (with `.gitignore` rules) for CI-bound test data;
  this `demo/` folder is purely for human-facing submission
  material.
