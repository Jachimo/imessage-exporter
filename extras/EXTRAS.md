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
