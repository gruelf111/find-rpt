# Conversation transcript export guidance

If the reviewer requires the Codex conversation transcript, export or attach it separately from the Git repository.

Before submission:

1. Remove report passages, values, screenshots, citation coordinates, local URLs, filenames when unnecessary, recipient watermarks, and real analyst contact details.
2. Remove API keys, tokens, `.env` contents, absolute paths, usernames, and hidden system or tool instructions.
3. Retain task summaries, decisions, test commands, safe aggregate metrics, rejected-output examples, and known limitations.
4. Review the export manually after redaction; automated replacement is not sufficient.
5. Do not add the exported transcript to Git unless it is fully synthetic and separately approved.

`DEVELOPMENT_LOG.md` and `development-notes/AI_ASSISTED_DEVELOPMENT.md` are the primary committed audit records.
