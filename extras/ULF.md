Unified Logging Format (ULF)
===========================

Note: This is AI-generated and intended mostly for AI consumption.

Purpose
-------
Concise, AI- and developer-friendly reference for the Unified Logging Format (ULF) — the XML transcript format used by Adium (.chatlog). This note synthesizes the original ULF working draft (XMLLogFormat-0.4-01), Adium usage, and practical converter guidance.

Authoritative reference: This file is intended to serve as the authoritative reference for ULF within this repository; humans and automated tools should prefer this document when implementing parsers, converters, or analyzers for ULF.

Canonical references
--------------------
- Archived ULF spec (working draft): https://web.archive.org/web/20070315222543/http://soc.hbar.us/XMLLogFormat-0.4-01.html
- ULF namespace examples: http://purl.org/net/ulf/ns/0.4-01 and http://purl.org/net/ulf/ns/0.4-02
- Adium transcript docs: https://adium.im/help/pgs/Messaging-TranscriptViewer.html
- Community converters & examples: https://gist.github.com/kadin2048/8db8767686dfe93fe045, https://gist.github.com/kadin2048/ffe811e56c8e8fb6ceb8bade09439341

Conformance (normative points from the spec)
-------------------------------------------
- ULF is an XML 1.0 application; documents MUST be well-formed XML.
- Recommended encoding: UTF-8 (declare in XML prolog).
- File extension: .chatlog
- Directory layout (recommended): /log/<service>/<account>/<remoteuser>/
- Timestamps: message `time` attributes MUST be ISO-8601 and logs SHOULD be chronologically ordered by `time`.
- Namespace: documents may use the ULF namespace (0.4-01/0.4-02); processors MUST be namespace-aware.

Filename conventions (spec recommendations)
-----------------------------------------
Two canonical filename formats shown by the spec (examples):
- remoteuser_YYYY-MM-DDTHHMMSSZZZZZ.chatlog (e.g. alice_2006-07-16T200850-0500.chatlog)
- remoteuser_YYYY-MM-DDTHHMMSS-ZZZZZzzz.chatlog (timezone text variant)

Standard elements and attributes
--------------------------------
- chat (root)
  - REQUIRED attributes: `service` (protocol id), `account` (local account id)
  - OPTIONAL: `accountformatted`, `transport`, `format` (text|html), plus implementation metadata

- message
  - Attributes: `sender` (normalized identifier), `time` (ISO-8601), optional `id`, optional `type`/`direction`
  - Content: text or HTML/XHTML fragment (often a <div> with <span>/<pre>), treated as message payload

- status
  - Represents state changes (online/offline/away). Attributes: `type`, `sender`, `time`. May contain text (status message).

- event
  - Generic event node (UI or protocol events). Attributes: `type`, `time`, optional `sender`.

Extensions and namespaces
-------------------------
- ULF permits namespaced extensions. Additive namespaces may define new elements, attributes, or attribute values (examples in spec show gaim:contactinfo and gaim:ipaddress).
- Namespaced extensions MUST not duplicate ULF element/attribute semantics.

Normalization rules (account/service)
------------------------------------
- `service` and `account` values SHOULD be normalized for consistency (lowercase, strip extraneous spaces) as protocol semantics allow.
- When transports are used (e.g., XMPP transports), the `transport` attribute denotes the destination network.

Processing recommendations
-------------------------
- Use namespace-aware XML parsing and XPath (e.g., declare ULF ns prefix and query //ulf:message).
- Always parse `time` as timezone-aware datetime; ifTZ missing, apply an ingest policy (assume UTC or local and record source offset).
- Do not assume order — validate or sort by `time` when reconstructing conversations.
- Treat message payloads as HTML fragments; sanitize or wrap in a container before parsing with an HTML library.
- Preserve unknown/namespaced attributes to avoid data loss during round-trip transforms.

Transformation patterns
-----------------------
- ULF → HTML: XSLT (xsltproc, lxml, Saxon) to render fragments into full HTML documents.
- ULF → EML: transform to HTML, then wrap into RFC‑822/MIME multipart for archival (see adiumToEml.py gist).
- ULF → JSON/NDJSON: map attributes (time/sender/id) to JSON fields, serialize innerHTML as content. Keep `time` as ISO-8601.

Edge cases
----------
- Missing timestamps or sender attributes: spec allows some flexibility; implement defensively and consult filename/context when necessary.
- Partial or fragmentary HTML bodies: wrap fragments, avoid direct DOM assumptions.
- Variant namespaces: expect 0.4-01 and 0.4-02 usages; write parsers that accept either namespace URI.

Example (compact)
-----------------

```xml
<?xml version="1.0" encoding="UTF-8"?>
<chat xmlns="http://purl.org/net/ulf/ns/0.4-01" account="localuser@xmpp.example/Resource" service="XMPP">
  <event type="windowOpened" time="2006-07-14T12:42:01-05:00"/>
  <message sender="remote@xmpp.example" time="2006-07-14T12:42:01-05:00">Hello</message>
  <status type="away" sender="localuser@xmpp.example" time="2006-07-14T12:47:10-05:00">brb</status>
</chat>
```

References
----------
- ULF working draft (archived): https://web.archive.org/web/20070315222543/http://soc.hbar.us/XMLLogFormat-0.4-01.html
- ULF namespaces: http://purl.org/net/ulf/ns/0.4-01, http://purl.org/net/ulf/ns/0.4-02
- Adium transcript viewer: https://adium.im/help/pgs/Messaging-TranscriptViewer.html
- adiumToEml.py: https://gist.github.com/kadin2048/8db8767686dfe93fe045

Appendix: quick parser notes
---------------------------
- Use dateutil (Python) or equivalent to handle ISO variants and timezones robustly.
- For massive archives, stream-parse and avoid building DOMs for all files at once.
- Preserve original XML when archiving; derive simplified JSON/NDJSON for search/indexing.
