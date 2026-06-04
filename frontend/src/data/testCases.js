export const QA_TEST_CATEGORIES = [
  {
    id: 'pdf-upload',
    label: 'PDF Upload',
    description: 'Validation, extraction, and error handling for incoming PDFs.',
  },
  {
    id: 'claim-extraction',
    label: 'Claim Extraction',
    description: 'LLM claim-extraction quality across document shapes and edge cases.',
  },
  {
    id: 'verdict-engine',
    label: 'Verdict Engine',
    description: 'Verdict labelling against live Tavily evidence on the trap document.',
  },
  {
    id: 'ui-testing',
    label: 'UI Testing',
    description: 'Frontend flow, state machine, and export behaviour.',
  },
]

export const QA_TEST_CASES = [
  {
    id: 'PU-01',
    category: 'pdf-upload',
    name: 'Rejects non-PDF extension',
    description: 'Upload a .docx file — backend returns 400 "Only PDF files are accepted".',
    status: 'pending',
  },
  {
    id: 'PU-02',
    category: 'pdf-upload',
    name: 'Rejects oversized file',
    description: 'Upload a PDF > MAX_FILE_SIZE_MB — backend returns 413 "File must be under {N}MB".',
    status: 'pending',
  },
  {
    id: 'PU-03',
    category: 'pdf-upload',
    name: 'Rejects non-PDF magic bytes',
    description: 'Upload a .pdf file with non-PDF content — backend returns 400 "Invalid PDF file".',
    status: 'pending',
  },
  {
    id: 'PU-04',
    category: 'pdf-upload',
    name: 'Extracts text from valid PDF',
    description: 'Upload a valid PDF — backend returns 200 with {filename, pages, text}.',
    status: 'pending',
  },
  {
    id: 'PU-05',
    category: 'pdf-upload',
    name: 'Handles image-only PDF',
    description: 'Upload a PDF with no extractable text — backend returns 422 "PDF contains no readable text".',
    status: 'pending',
  },

  {
    id: 'CE-01',
    category: 'claim-extraction',
    name: 'Extracts known claims from trap document',
    description: 'Verify trap document yields the expected 5–8 claims (Tesla 1.8M, ChatGPT 100M, water, Python, OpenAI, etc.).',
    status: 'pending',
  },
  {
    id: 'CE-02',
    category: 'claim-extraction',
    name: 'Enforces MAX_CLAIMS=20 cap',
    description: 'Upload a dense PDF (>=20 candidates) — pipeline truncates to 20 and logs WARNING.',
    status: 'pending',
  },
  {
    id: 'CE-03',
    category: 'claim-extraction',
    name: 'Returns [] on extraction failure',
    description: 'Simulate LLM failure — endpoint returns 200 with empty claims list (no 5xx).',
    status: 'pending',
  },
  {
    id: 'CE-04',
    category: 'claim-extraction',
    name: 'Strips markdown code fences',
    description: 'Model occasionally returns ```json ... ``` — service must strip before parsing.',
    status: 'pending',
  },
  {
    id: 'CE-05',
    category: 'claim-extraction',
    name: 'Skips invalid items gracefully',
    description: 'Model returns mixed valid/invalid records — valid items preserved, invalid skipped.',
    status: 'pending',
  },
  {
    id: 'CE-06',
    category: 'claim-extraction',
    name: 'Labels claim types correctly',
    description: 'Type field is one of: statistic | financial | date | technical | attribution.',
    status: 'pending',
  },
  {
    id: 'CE-07',
    category: 'claim-extraction',
    name: 'Handles empty / short text',
    description: 'Upload a near-empty PDF — endpoint returns [] (not 5xx).',
    status: 'pending',
  },

  {
    id: 'VE-01',
    category: 'verdict-engine',
    name: 'Trap document baselines',
    description: '8 trap claims produce expected verdicts (see docs/TruthLayer_Build_Guide.md table).',
    status: 'pending',
  },
  {
    id: 'VE-02',
    category: 'verdict-engine',
    name: 'Empty evidence short-circuits to false',
    description: 'Tavily returns [] — verdict is false with explanation "No evidence found to evaluate this claim."',
    status: 'pending',
  },
  {
    id: 'VE-03',
    category: 'verdict-engine',
    name: 'Defensive fallback on per-claim failure',
    description: 'Forced exception in search/verdict — claim still gets a fallback VerifiedClaim (id reassigned 1..N).',
    status: 'pending',
  },
  {
    id: 'VE-04',
    category: 'verdict-engine',
    name: 'Summary stats add up',
    description: 'summary.{total, verified, inaccurate, false} consistent with len(claims) and per-claim verdicts.',
    status: 'pending',
  },

  {
    id: 'UI-01',
    category: 'ui-testing',
    name: 'Upload → Processing → Results flow',
    description: 'End-to-end: dropzone accepts PDF, processing screen advances through 4 steps, results render.',
    status: 'pending',
  },
  {
    id: 'UI-02',
    category: 'ui-testing',
    name: 'Long-running hint appears at 30s',
    description: 'Processing screen shows "this is taking longer than usual" copy after 30s.',
    status: 'pending',
  },
  {
    id: 'UI-03',
    category: 'ui-testing',
    name: 'Cancel returns to upload',
    description: 'Cancel button on processing screen resets state and returns to upload.',
    status: 'pending',
  },
  {
    id: 'UI-04',
    category: 'ui-testing',
    name: 'View Report opens new window',
    description: 'Clicking "View Report" opens a new tab/window with the verification report (light theme).',
    status: 'pending',
  },
  {
    id: 'UI-05',
    category: 'ui-testing',
    name: 'Export Report triggers print dialog',
    description: 'Clicking "Export Report" opens new window and auto-triggers window.print() for Save-as-PDF.',
    status: 'pending',
  },
]

export function getTestCasesByCategory(categoryId) {
  return QA_TEST_CASES.filter((c) => c.category === categoryId)
}
