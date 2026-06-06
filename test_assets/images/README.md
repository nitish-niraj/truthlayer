# images/

Real image files used as the image pipeline input for the regression suite.
Supported formats: PNG, JPG, JPEG, WEBP.

For each file, add an entry to `test_assets/expected_results.json`:

```json
"screenshot.png": { "verified": 2, "inaccurate": 1, "false": 0 }
```
