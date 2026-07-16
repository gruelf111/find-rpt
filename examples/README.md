# Local example workflow

Committed examples are synthetic and contain no report-derived text. Generate real-corpus output only into an ignored local directory, never commit it, and delete it after review.

```text
python skills/find-rpt/scripts/find_rpt.py --command '/find-rpt BP/ LN 22 Jun 2026 "J.P. Morgan"' > .cache/local-example.json
python scripts/redact_example.py .cache/local-example.json .cache/redacted-example.json
```

The redactor removes common identifiers and free-text fields but is not an approval to publish. Manually inspect every line and keep both real and redacted transcripts local unless the result is fully synthetic.

See `synthetic-runs.md` for a complete brief with a citation, a not-found result, and a no-send escalation draft.
