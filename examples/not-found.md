# Synthetic not-found result

Command:

```text
/find-rpt XYZ LN 2026-06-22 "Example Broker"
```

Result:

```json
{
  "schema_version": "1.0",
  "status": "not_found",
  "normalized_request": {
    "ticker": "XYZ LN",
    "date": "2026-06-22",
    "broker": "Example Broker"
  },
  "message": "No ticker evidence was found in the first two pages of the shortlisted files.",
  "requires_analyst_escalation": false,
  "email_draft": null,
  "sent": false
}
```

`ambiguous` follows the same stop behavior but includes safe candidate metadata. The skill never chooses one of the candidates manually.
