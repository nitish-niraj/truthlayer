# Screenshots

Full-resolution screenshots of the TruthLayer production deployment, in
walkthrough order.

---

## 1. Home — Upload

![Homepage](screenshots/homepage.png)

The landing screen — drag-and-drop a PDF or click to browse.

---

## 2. File Picker

![File select](screenshots/fileselect.png)

Native file picker integration with PDF-only validation. The dropzone
rejects anything that is not a `.pdf` and shows a clear error message.

---

## 3. File Selected

![Selected file](screenshots/selected-file.png)

The dropzone confirms the file is queued for analysis. The user can
swap to a different file or click **Analyze Document** to start the
pipeline.

---

## 4. Analyzing

![Analyzing](screenshots/analyzing.png)

Live stepper with rotating status messages during claim extraction,
search, and verdict generation. The progress bar fills smoothly while
the server reports progress.

---

## 5. Results — Output

![Output](screenshots/output.png)

Per-claim verdicts with explanations, corrected facts, and source URLs.
The colour code is green (verified), amber (inaccurate), red (false).

---

## 6. Results — Output (continued)

![Output 2](screenshots/output2.png)

The dashboard scrolls to reveal all claims, even for long documents.
Each claim is collapsible and includes a **Source** link to the
evidence URL.

---

## 7. Verification Report

![Report](screenshots/report.png)

The structured verification report — shareable, print-ready, and
suitable for compliance or legal review.

---

## 8. Verification Report (continued)

![Report 2](screenshots/report2.png)

Every claim with its evidence-backed verdict in one scrollable view.

---

## 9. Export Report

![Export report](screenshots/export-report.png)

The export flow produces a print-formatted report suitable for sharing
with stakeholders. Click **Export Report** in the dashboard to open
the print dialog with the report pre-loaded.
