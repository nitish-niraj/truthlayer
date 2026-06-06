# trap_images/

Hand-curated "trick" images. These are deliberately designed to expose
common failure modes in the vision pipeline:

- **bar-chart-ev-sales.png** — bar chart where every label must be read off
  the axis and translated into a full sentence.
- **pie-chart-energy-mix.png** — pie chart with overlapping labels.
- **infographic-misleading.png** — infographic with a single outlier
  claim that contradicts published statistics.
- **social-screenshot-attribution.png** — screenshot of a tweet with a
  verifiable number, attribution type.

Each trap should produce at least one claim whose verdict the regression
test can pin down. Add the expected distribution to
`expected_results.json`.
