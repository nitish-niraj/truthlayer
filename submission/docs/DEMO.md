# Demo Video

A complete end-to-end walkthrough of TruthLayer.

**File:** [`demo/truth-layers.mp4`](demo/truth-layers.mp4)

---

## What the video covers

The video is a 90-second screen recording of the production deployment
at [https://truthlayernitish.vercel.app](https://truthlayernitish.vercel.app),
showing every stage of the user journey.

### 1. Uploading a PDF

- Open the homepage
- Drag a PDF onto the dropzone (or click to browse)
- The dropzone confirms the file is queued
- Click **Analyze Document** to start the pipeline

### 2. Processing workflow

- The processing screen shows a live stepper
- Each stage — *Extracting Text → Identifying Claims → Searching Live
  Sources → Generating Verdicts* — lights up as the server reports
  progress
- Rotating status messages explain what the pipeline is doing at each
  moment
- The progress bar fills smoothly to 100 %

### 3. Results dashboard

- The summary bar shows total / verified / inaccurate / false counts
- Each claim is rendered as a colour-coded card:
  - **Green** — verified
  - **Amber** — inaccurate
  - **Red** — false
- Every card includes the claim, the explanation, the corrected fact
  (when applicable), and the source URL

### 4. Export report

- Click **View Report** to open a print-formatted verification report
  in a new tab
- Click **Export Report** to open the browser's print dialog with the
  report pre-loaded — save as PDF or send to a printer

---

## Video file

- **Path:** `docs/demo/truth-layers.mp4`
- **Format:** MP4 (H.264)
- **Duration:** ~90 seconds
- **Resolution:** 1080p

If your browser cannot render the video inline, you can download the
file directly from
[`docs/demo/truth-layers.mp4`](demo/truth-layers.mp4).
