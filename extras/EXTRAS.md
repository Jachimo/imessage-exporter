Extras
======

These files are provided as add-ons for `imessage-extractor` and as
inspiration for other uses.

conversationsplit.py
--------------------

Split JSON message exports into logical 'conversations' for further
processing or storage. 

Usage:

    python3 extras/conversationsplit.py --input <file|dir> --out-dir <out> [--idle-seconds N] [--min-messages M] [--max-duration S]

- Input: either a file or directory.
- Only `.ndjson` and `.json` files are processed.
- Grouping: by `chat_id` if present (else by stable participant handle set).
- Split rule: new conversation when gap >= `--idle-seconds`; optional
  `--max-duration` further splits very long convos.
- Small convos (less than `--min-messages`) are merged into previous convo.
- Output: Directory to write output NDJSON files, one per conversation

TODO: The filenames this script produces could probably be nicer.


ULF (Unified Logging Format)
---------------------------

The file `ULF.md` contains an AI-readable description of the "Unified
Logging Format" (ULF) for chat archives, originally introduced by
Adium. It includes schema notes, processing guidance, and links to
primary sources. **Don't trust the contents without verifying.**

Human readers probably want:

- Kadin2048's [Instant Messaging Client Log
  Formats](https://gist.github.com/kadin2048/ffe811e56c8e8fb6ceb8bade09439341);
  noted as being last updated in 2021.
- [Adium Github Repository](https://github.com/adium/adium/); this is
  the de facto "reference implementation" of ULF.
- Microformats [chat-formats
  page](https://microformats.org/wiki/chat-formats); notes the format
  was intended to be used by Adium, Gaim, and Kopete.
- [Unified Logging Format Spec](http://purl.org/NET/ULF/SPEC); despite
  being a PURL, it's now a dead link. Most recent version on the
  Internet Archive seems to be [version 0.4-01 from Mar
  2007](https://web.archive.org/web/20070315222543/http://soc.hbar.us/XMLLogFormat-0.4-01.html).

ndjson_to_ulf.py
----------------

Convert NDJSON exports into ULF `.chatlog` files (ULF 0.4 style plus an `imex` extension namespace to preserve metadata such as GUIDs, rowids, attachments, and participants).

Usage (short):

    python3 extras/ndjson_to_ulf.py --input <file|dir> --out-dir <out> [--idle-seconds N] [--max-duration S] [--service iMessage] [--account unknown]

Notes:

- Reads a single NDJSON file or recursively all matching `--glob` under a directory.
- Groups by chat_id or participant set, sorts by time, splits on idle gap (and optional max duration).
- Emits one `.chatlog` per conversation under `/log/<service>/<account>/<chat>/`.
- Keeps attachment paths and other fields via the `imex` namespace to avoid data loss.
