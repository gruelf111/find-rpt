---
description: Find and brief one report from the configured local sell-side corpus
argument-hint: <ticker> <date> <broker>
allowed-tools: Bash(python *)
---

Pass the complete argument string to the shared thin launcher:

```text
python skills/find-rpt/scripts/find_rpt.py --command "/find-rpt $ARGUMENTS"
```

Read `skills/find-rpt/references/output-contract.md`. Return the launcher's `rendered_markdown` unchanged for `found` or `partial`; report other statuses transparently. Preserve citations. Do not inspect PDFs, recalculate values, add external knowledge, or duplicate pipeline logic. If an analyst draft is present, display it and stop. Never send email or launch a mail client.
