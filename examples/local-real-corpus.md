# Generating local real-corpus examples

Real-report output may contain proprietary text and analyst contact details. Keep it in the ignored `.cache/` directory, review it locally, and do not commit or redistribute it.

```powershell
python skills/find-rpt/scripts/find_rpt.py --command '/find-rpt TICKER EXCHANGE YYYY-MM-DD "Broker Name"' > .cache/local-example.json
python scripts/redact_example.py .cache/local-example.json .cache/redacted-example.json
```

Structural redaction is not publication approval. Before sharing anything, manually remove or replace:

- report titles, takeaways, rationale, values, and quoted or paraphrased passages;
- PDF filenames and hashes unless disclosure is necessary and permitted;
- analyst names, email addresses, phone numbers, and recipient watermarks;
- citation IDs, local URLs, coordinates, screenshots, and absolute paths; and
- any fact that could reconstruct proprietary report content.

Prefer the committed synthetic examples for submission. If the assignment permits local screenshots or transcripts, attach them separately after a line-by-line human review; never add them to Git.
