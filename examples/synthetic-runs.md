# Synthetic `/find-rpt` runs

These examples are fabricated and safe to commit.

## Complete brief with inline citation

**ABC LN - Example Broker - 22 Jun 2026**

# Synthetic Company: pricing supports earnings [source](http://127.0.0.1:8765/citation/cit-0123456789abcdef01234567#evidence-target)

Pricing supports the synthetic earnings outlook. [source](http://127.0.0.1:8765/citation/cit-0123456789abcdef01234567#evidence-target)

## What changed

| Metric | Period | Old | New | Revision | Consensus |
| --- | --- | ---: | ---: | ---: | ---: |
| Adjusted EPS [source](http://127.0.0.1:8765/citation/cit-0123456789abcdef01234567#evidence-target) | FY2027E | 1.20 EUR/share | 1.30 EUR/share | +8.3% | 1.10 EUR/share |

## Estimate picture

```text
EPS FY2027E (EUR/share)
Old                  |█████████   1.2
New                  |██████████  1.3
Consensus            |████████    1.1
```

## Not found

```json
{"schema_version":"1.0","status":"not_found","normalized_request":{"ticker":"XYZ LN","date":"2026-06-22","broker":"Example Broker"},"message":"No ticker evidence was found.","sent":false}
```

## Escalation with missing analyst address

```text
To: [TODO: address]
Subject: Question on revised estimates for ABC LN

Dear Synthetic Analyst,

Could you clarify which synthetic operating assumptions drove the FY2027E adjusted EPS revision?

Best,
[Your name]

This draft has not been sent.
```
