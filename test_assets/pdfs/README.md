# pdfs/

Real PDF documents used as the PDF pipeline input for the regression suite.

Drop `.pdf` files here. For each, add an entry to
`test_assets/expected_results.json`:

```json
"report-name.pdf": { "verified": 3, "inaccurate": 1, "false": 0 }
```
