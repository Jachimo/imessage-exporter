#!/usr/bin/env python3
"""
Convert NDJSON exports from imessage-exporter into ULF (.chatlog) XML files.

- Accepts a single NDJSON file or a directory of NDJSON files.
- Groups messages by chat_id or participant handle set, splits conversations by idle gap.
- Emits ULF 0.4-style XML, with an extension namespace to preserve implementation-specific metadata
- Keeps attachment paths relative when possible

Dependencies: Python 3 stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import uuid
import glob
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple
import xml.etree.ElementTree as ET

# Unified Logging Format namespace
ULF_NS = "http://purl.org/net/ulf/ns/0.4-01"

# Extension namespace for extra stuff
IMEX_NS = "http://github.com/Jachimo/ns/ulf-ext/0.1"

ET.register_namespace("", ULF_NS)
ET.register_namespace("imex", IMEX_NS)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Convert NDJSON exports into ULF (.chatlog) files")
    p.add_argument("--input", "-i", required=True, help="Input NDJSON file or directory")
    p.add_argument("--out-dir", "-o", required=True, help="Output directory root for .chatlog files")
    p.add_argument("--idle-seconds", type=int, default=14400, help="Idle gap (seconds) to split conversations")
    p.add_argument("--max-duration", type=int, default=604800, help="Optional max duration per conversation (seconds); 0 = no limit")
    p.add_argument("--glob", default="**/*.ndjson", help="Glob used when input is a directory (default **/*.ndjson)")
    p.add_argument("--service", default="iMessage", help="Service name to store in chat.service")
    p.add_argument("--account", default="Me", help="Local account identifier to store in chat.account")
    p.add_argument("--dry-run", action="store_true", help="Do not actually write files")
    p.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    return p.parse_args()


def parse_date_iso(val: str) -> datetime:
    """ Wrapper around datetime.fromisoformat() that correctly handles Zulu time """
    if val.endswith("Z"):
        val = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(val)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def read_ndjson_file(path: str) -> Iterable[Dict[str, Any]]:
    """ Iterates through an NDJSON file one object at a time.
    NDJSON is just a series of JSON objects, one per line, with minimal escaping.
    """ 
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)  # return type: https://docs.python.org/3/library/json.html#json-to-py-table
                yield obj
            except json.JSONDecodeError:
                # TODO: At least in verbose mode we should note skipped lines
                continue


def iter_messages(input_path: str, glob_pattern: str, verbose: bool) -> Iterable[Dict[str, Any]]:
    """ Given an input path that can be a single file or a directory to search recursively,
    parse each input file as NDJSON and iterate through the objects in each.
    """
    if os.path.isfile(input_path):
        # Simple case of one file as input
        files = [input_path]
    else:
        # Search recursively down the dir tree for matching candidate files
        files = glob.glob(os.path.join(input_path, glob_pattern), recursive=True)
    if verbose:
        print(f"Found {len(files)} file(s)")
    for f in files:
        if verbose:
            print(f"Reading {f}")
        for msg in read_ndjson_file(f):
            # Implicit assumption here that msg is a dict, because each NDJSON line is a JSON object
            msg["_source"] = os.path.basename(f)
            msg["_parsed_date"] = parse_date_iso(msg.get("date_iso") or msg.get("date"))  # I regret this choice of name
            yield msg


def chat_key(msg: Dict[str, Any]) -> str:
    """ Produce the "chat key" for a message.
    The chat key is the chat_id if that exists; if it doesn't, it's the message handles
    """
    if msg.get("chat_id") is not None:
        return f"chat:{msg['chat_id']}"
    handles: List[str] = []
    sender = msg.get("sender") or {}
    if isinstance(sender, dict):
        h = sender.get("handle")
        if h:
            handles.append(h)
    for r in msg.get("recipients") or []:
        if isinstance(r, dict):
            h = r.get("handle")
            if h:
                handles.append(h)
        elif isinstance(r, str):
            handles.append(r)
    if handles:
        return "handles:" + ",".join(sorted(set(handles)))
    return "chat:unknown"


def group_and_split(messages: Iterable[Dict[str, Any]], idle_seconds: int, max_duration: int) -> Dict[str, List[List[Dict[str, Any]]]]:
    """ Split messages into logical 'conversations' or 'chats' (in ULF terminology),
    which don't exist natively in iMessage or iOS SMS logs (just one looooong log per handle).
    - idle_seconds = max time in seconds between messages before we consider it a new conversation
    - max_duration = maximum length of a conversation before a split is forced
    """
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for m in messages:
        key = chat_key(m)
        grouped.setdefault(key, []).append(m)
    result: Dict[str, List[List[Dict[str, Any]]]] = {}
    for key, msgs in grouped.items():
        msgs.sort(key=lambda m: m.get("_parsed_date") or datetime.fromtimestamp(0, tz=timezone.utc))
        conversations: List[List[Dict[str, Any]]] = []
        current: List[Dict[str, Any]] = []
        for m in msgs:
            if not current:
                current.append(m)
                continue
            prev = current[-1]
            prev_dt = prev.get("_parsed_date")  # "_parsed_date" is the message date, which has been parsed
            cur_dt = m.get("_parsed_date")  # it's *not* the date/time when the message was parsed
            delta = 0
            if prev_dt and cur_dt:
                delta = int((cur_dt - prev_dt).total_seconds())
            if delta >= idle_seconds:
                conversations.append(current)
                current = [m]
            else:
                current.append(m)
        if current:
            conversations.append(current)

        if max_duration and max_duration > 0:
            split: List[List[Dict[str, Any]]] = []
            for conv in conversations:
                if len(conv) <= 1:
                    split.append(conv)
                    continue
                start_idx = 0
                for i in range(1, len(conv)):
                    start_dt = conv[start_idx].get("_parsed_date") or datetime.fromtimestamp(0, tz=timezone.utc)
                    cur_dt = conv[i].get("_parsed_date") or datetime.fromtimestamp(0, tz=timezone.utc)
                    if int((cur_dt - start_dt).total_seconds()) > max_duration:
                        split.append(conv[start_idx:i])
                        start_idx = i
                split.append(conv[start_idx:])
            conversations = split

        result[key] = conversations
    return result


def slugify(val: str, limit: int = 20) -> str:
    """ Make filename 'slug' URL-safe-ish """
    import re
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", val)
    slug = slug.strip("-").lower()
    if not slug:
        slug = "unknown"
    return slug[:limit]


def format_time_for_filename(dt: Optional[datetime]) -> Optional[str]:
    """ Formats time per the ULF spec for inclusion in output file names.
    It's sort of like a ISO-flavored DTG.
    """
    if not dt:
        return None
    try:
        dt_utc = dt.astimezone(timezone.utc)
        s = dt_utc.strftime("%Y%m%dT%H%M%SZ")
        return s
    except Exception:
        return None


def to_iso8601(dt: Optional[datetime]) -> Optional[str]:
    if not dt:
        return None
    try:
        return dt.isoformat()
    except Exception:
        return None


def build_message_elements(parent: ET.Element, msgs: List[Dict[str, Any]]) -> None:
    for m in msgs:
        
        # ULF <message> components
        msg_el = ET.SubElement(parent, ET.QName(ULF_NS, "message"))
        sender = None
        snd = m.get("sender")
        if isinstance(snd, dict):
            sender = snd.get("handle") or snd.get("display_name")
        if not sender:
            sender = "unknown"
        msg_el.set("sender", sender)
        t = to_iso8601(m.get("_parsed_date"))
        if t:
            msg_el.set("time", t)
        if "guid" in m:
            msg_el.set(ET.QName(IMEX_NS, "guid"), str(m.get("guid")))
        if "rowid" in m:
            msg_el.set(ET.QName(IMEX_NS, "rowid"), str(m.get("rowid")))
        if "is_from_me" in m:
            msg_el.set(ET.QName(IMEX_NS, "direction"), "out" if m.get("is_from_me") else "in")
        text = m.get("text")
        if text is None:
            text = ""
        msg_el.text = text

        # Attachments
        for att in m.get("attachments") or []:
            att_el = ET.SubElement(msg_el, ET.QName(IMEX_NS, "attachment"))
            if att.get("filename"):
                att_el.set("filename", str(att["filename"]))
            if att.get("mime_type"):
                att_el.set("mime_type", str(att["mime_type"]))
            if att.get("size") is not None:
                att_el.set("size", str(att["size"]))
            if att.get("path"):
                att_el.set("path", str(att["path"]))

        # Recipients
        recips = m.get("recipients") or []
        for r in recips:
            if isinstance(r, dict):
                r_el = ET.SubElement(msg_el, ET.QName(IMEX_NS, "recipient"))
                if r.get("handle"):
                    r_el.set("handle", str(r["handle"]))
                if r.get("display_name"):
                    r_el.set("display_name", str(r["display_name"]))
                if r.get("is_me") is not None:
                    r_el.set("is_me", "true" if r.get("is_me") else "false")


def write_chatlog(out_dir: str, service: str, account: str, key: str, conv: List[Dict[str, Any]], dry_run: bool, verbose: bool) -> str:
    start = conv[0].get("_parsed_date")
    end = conv[-1].get("_parsed_date")
    ts = format_time_for_filename(end)  # use end time (last message) as overall timestamp for chat
    
    chat_slug = slugify(key.replace("chat:", "").replace("handles:", ""))
    
    fname = f"{chat_slug}_{ts}.chatlog"

    # Construct output dir tree per ULF recommendations (not normative)
    root_dir = os.path.join(out_dir, slugify(account))
    os.makedirs(root_dir, exist_ok=True)
    out_path = os.path.join(root_dir, fname)

    # Begin building the XML structure
    chat_el = ET.Element(ET.QName(ULF_NS, "chat"), attrib={"service": service, "account": account})
    chat_el.set(ET.QName(IMEX_NS, "chat_key"), key)
    
    chat_el.set(ET.QName(IMEX_NS, "start_time"), to_iso8601(start) or "")
    chat_el.set(ET.QName(IMEX_NS, "end_time"), to_iso8601(end) or "")

    # Participants summary
    participants = conv[0].get("recipients") or []
    for p in participants:
        if isinstance(p, dict):
            p_el = ET.SubElement(chat_el, ET.QName(IMEX_NS, "participant"))
            if p.get("handle"):
                p_el.set("handle", str(p["handle"]))
            if p.get("display_name"):
                p_el.set("display_name", str(p["display_name"]))
            if p.get("is_me") is not None:
                p_el.set("is_me", "true" if p.get("is_me") else "false")

    # Add all the messages in the conversation/chat
    build_message_elements(chat_el, conv)

    # Write it out (or just talk about it)
    tree = ET.ElementTree(chat_el)
    if dry_run:
        if verbose:
            print(f"DRY-RUN would write: {out_path}")
        return out_path
    tree.write(out_path, encoding="utf-8", xml_declaration=True)
    if verbose:
        print(f"Wrote {out_path}")
    return out_path


def main() -> None:
    args = parse_args()
    msgs = list(iter_messages(args.input, args.glob, args.verbose))
    grouped = group_and_split(msgs, args.idle_seconds, args.max_duration)
    total_files = 0
    for key, conversations in grouped.items():
        for conv in conversations:
            write_chatlog(args.out_dir, args.service, args.account, key, conv, args.dry_run, args.verbose)
            total_files += 1
    print(f"Finished: chats={len(grouped)} files_written={total_files} (dry_run={args.dry_run})")


if __name__ == "__main__":
    main()
