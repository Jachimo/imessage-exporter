#!/usr/bin/env python3
"""
conversationsplit.py

Reads ND-JSON message exports produced by `imessage-exporter` and splits them
into logical "conversations", each in a separate file

Each output file is NDJSON (one JSON message per line) with collision-resistant, reasonably sortable filenames.

Usage:
  python3 extras/conversationsplit.py --input-dir /tmp/exports --out-dir /tmp/convos --idle-seconds 1800

Use the --help option for a summary of options.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import glob
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Any, Tuple, Optional

# Configure basic logging; callers can override
logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.INFO)


def parse_args():
    p = argparse.ArgumentParser(description="Split NDJSON/JSON message exports into conversations by idle time")
    p.add_argument("--input", "-i", required=True, help="Input file or directory")
    p.add_argument("--out-dir", "-o", default="./conversations", help="Directory to write conversation files")
    p.add_argument("--idle-seconds", type=int, default=14400, help="Seconds of inactivity that define a new conversation (default 14400s = 4hrs)")
    p.add_argument("--min-messages", type=int, default=2, help="Minimum messages per conversation; smaller ones are merged into previous (default 2)")
    p.add_argument("--max-duration", type=int, default=604800, help="Max duration in seconds for a conversation; 0 = no limit (default 604800 = 1wk")
    p.add_argument("--glob", default="**/*.{ndjson,json}", help="Glob to find input files under input path when input is a directory (default to .json and .ndjson)")
    p.add_argument("--dry-run", action="store_true", help="Do not write files, just print planned actions")
    p.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    return p.parse_args()


def parse_date_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    # Accept ISO with Z or offset and ensure timezone-aware datetime
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        # Make timezone-aware (assume UTC if none provided)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        try:
            # Try as integer epoch seconds
            return datetime.fromtimestamp(int(s), tz=timezone.utc)
        except Exception:
            return None


def read_ndjson(path: str):
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                # skip invalid lines but warn
                logging.warning("Skipping invalid JSON line %d in %s", lineno, path)


def read_json_array(path: str):
    with open(path, "r", encoding="utf-8") as fh:
        try:
            data = json.load(fh)
        except Exception as e:
            logging.error("Error reading JSON array from %s: %s", path, e)
            return
        if isinstance(data, list):
            for obj in data:
                yield obj
        else:
            logging.warning("JSON file %s does not contain an array; attempting to read line-by-line", path)
            for obj in read_ndjson(path):
                yield obj


def iter_messages_from_file(path: str):
    lower = path.lower()
    if lower.endswith(".ndjson"):
    	# Correctly-suffixed NDJSON is easy
        yield from read_ndjson(path)
    elif lower.endswith(".json"):
        # If suffix is just .json, try to determine if it's *really* JSON or NDJSON
        with open(path, "r", encoding="utf-8") as fh:
            head = fh.read(1024)
        # Not elegant, but we can look at the first non-whitespace character...
        if head.lstrip().startswith("["):
            yield from read_json_array(path)
        else:
            yield from read_ndjson(path)
    else:
        # fallback: treat as NDJSON
        yield from read_ndjson(path)


def make_chat_key(msg: Dict[str, Any]) -> str:
    # Prefer chat_id if present and non-empty
    chat_id = msg.get("chat_id") or msg.get("chat_guid")
    if chat_id:
        return f"chat:{chat_id}"
    # Fallback: compose from participant handles
    handles = set()
    sender = msg.get("sender") or {}
    s_handle = sender.get("handle") if isinstance(sender, dict) else None
    if s_handle:
        handles.add(s_handle)
    for r in msg.get("recipients") or []:
        if isinstance(r, dict):
            h = r.get("handle")
            if h:
                handles.add(h)
        elif isinstance(r, str):
            handles.add(r)
    if handles:
        sorted_handles = sorted(handles)
        return "handles:" + ",".join(sorted_handles)
    # ultimate fallback
    return "chat:unknown"


def group_messages_by_chat(input_path: str, glob_pattern: str, verbose: bool = False) -> Dict[str, List[Dict[str, Any]]]:
    # If input_path is a file, process just that file; if it's a directory, recurse using glob_pattern
    files: List[str] = []
    if os.path.isfile(input_path):
        files = [input_path]
    elif os.path.isdir(input_path):
        # Expand brace-style patterns like **/*.{ndjson,json}
        base = input_path
        patterns: List[str] = []
        if "{" in glob_pattern and "}" in glob_pattern:
            pre, rest = glob_pattern.split("{", 1)
            inner, post = rest.split("}", 1)
            for choice in inner.split(','):
                patterns.append(os.path.join(base, pre + choice + post))
        else:
            patterns.append(os.path.join(base, glob_pattern))
        # Collect files from all patterns
        seen = set()
        for pat in patterns:
            for m in glob.glob(pat, recursive=True):
                if m not in seen:
                    seen.add(m)
                    files.append(m)
    else:
        # treat as glob relative to cwd
        pattern = input_path
        files = glob.glob(pattern, recursive=True)
    if verbose:
        logging.info("Found %d files for input %s", len(files), input_path)
    groups: Dict[str, List[Dict[str, Any]]] = {}
    total = 0
    for f in files:
        # Only consider .json and .ndjson files
        low = f.lower()
        if not (low.endswith('.json') or low.endswith('.ndjson')):
            if verbose:
                logging.debug("Skipping non-json file: %s", f)
            continue
        if verbose:
            logging.info("Reading %s", f)
        for msg in iter_messages_from_file(f):
            key = make_chat_key(msg)
            # annotate with parsed timestamp for easier sorting
            d = parse_date_iso(msg.get("date_iso") or msg.get("date"))
            msg.setdefault("_parsed_date" , None)
            if d:
                msg["_parsed_date"] = d
            # keep origin info
            msg.setdefault("_source_file", os.path.basename(f))
            groups.setdefault(key, []).append(msg)
            total += 1
    if verbose:
        logging.info("Total messages read: %d; chats: %d", total, len(groups))
    return groups


def split_group_into_conversations(messages: List[Dict[str, Any]], idle_seconds: int, max_duration: int = 0) -> List[List[Dict[str, Any]]]:
    # Sort messages by parsed date (None => far past)
    def date_or_min(m):
        d = m.get("_parsed_date")
        if d is None:
            return datetime.fromtimestamp(0, tz=timezone.utc)
        return d

    messages = sorted(messages, key=date_or_min)
    convos: List[List[Dict[str, Any]]] = []
    current: List[Dict[str, Any]] = []
    for msg in messages:
        if not current:
            current.append(msg)
            continue
        prev = current[-1]
        prev_d = prev.get("_parsed_date")
        cur_d = msg.get("_parsed_date")
        if prev_d is None or cur_d is None:
            # If either missing, use idle boundary (conservative: treat as continuous)
            delta = 0
        else:
            delta = int((cur_d - prev_d).total_seconds())
        if delta >= idle_seconds:
            convos.append(current)
            current = [msg]
        else:
            current.append(msg)
    if current:
        convos.append(current)
    # Enforce max_duration by further splitting convos that are too long
    if max_duration and max_duration > 0:
        new_convos: List[List[Dict[str, Any]]] = []
        for c in convos:
            if len(c) <= 1:
                new_convos.append(c)
                continue
            start_idx = 0
            for i in range(1, len(c)):
                start_d = c[start_idx].get("_parsed_date") or datetime.fromtimestamp(0, tz=timezone.utc)
                cur_d = c[i].get("_parsed_date") or datetime.fromtimestamp(0, tz=timezone.utc)
                if int((cur_d - start_d).total_seconds()) > max_duration:
                    new_convos.append(c[start_idx:i])
                    start_idx = i
            new_convos.append(c[start_idx:])
        convos = new_convos
    return convos


def merge_small_conversations(convos: List[List[Dict[str, Any]]], min_messages: int) -> List[List[Dict[str, Any]]]:
    if min_messages <= 1:
        return convos
    merged: List[List[Dict[str, Any]]] = []
    for c in convos:
        if not merged:
            merged.append(c)
            continue
        if len(c) < min_messages:
            # merge into previous
            merged[-1].extend(c)
        else:
            merged.append(c)
    return merged


def ensure_out_dir(path: str):
    os.makedirs(path, exist_ok=True)


def write_conversation(out_dir: str, chat_key: str, conv: List[Dict[str, Any]], dry_run: bool = False) -> str:
    # Filename format: {CHATKEY}-{YYYYMMDD}T{HHMMSS}Z.ndjson where CHATKEY is first 8 hex of blake2b(chat_key)
    import hashlib

    # timestamp from last message in conv (end)
    end = conv[-1].get("_parsed_date")
    if isinstance(end, datetime):
        try:
            end_utc = end.astimezone(timezone.utc)
            ts = end_utc.strftime("%Y%m%dT%H%M%SZ")
        except Exception:
            ts = "unknown"
    else:
        ts = "unknown"

    # Short (4 dig) hash value to group conversations from the same log file ('chat')
    h = hashlib.blake2b(chat_key.encode("utf-8"), digest_size=4).hexdigest()

    fname = f"{h}-{ts}.ndjson"
    out_path = os.path.join(out_dir, fname)
    if dry_run:
        return out_path
    with open(out_path, "w", encoding="utf-8") as fh:
        for msg in conv:
            # remove internal data before writing
            to_write = {k: v for k, v in msg.items() if not k.startswith("_")}
            fh.write(json.dumps(to_write, ensure_ascii=False) + "\n")
    return out_path


def main():
    args = parse_args()
    groups = group_messages_by_chat(args.input, args.glob, args.verbose)
    ensure_out_dir(args.out_dir)
    total_written = 0
    total_convos = 0
    for chat_key, msgs in groups.items():
        if args.verbose:
            logging.info("Processing chat %s with %d messages", chat_key, len(msgs))
        convos = split_group_into_conversations(msgs, args.idle_seconds, args.max_duration)
        convos = merge_small_conversations(convos, args.min_messages)
        for c in convos:
            out_path = write_conversation(args.out_dir, chat_key, c, dry_run=args.dry_run)
            if args.verbose or args.dry_run:
                logging.info(("DRY-RUN: " if args.dry_run else "Wrote: ") + out_path)
            total_written += 1
        total_convos += len(convos)
    logging.info("Finished: chats=%d conversations=%d files_written=%d", len(groups), total_convos, total_written)


if __name__ == "__main__":
    main()
