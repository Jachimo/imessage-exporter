<!-- SPDX-License-Identifier: MIT -->
# iOS Address Book (Contacts) SQLite Schema

If available, an Apple Address Book SQLite database file can be used to enrich message exports, particularly by resolving the phone numbers associated with messages back to real names. 

The database, which is typically named "AddressBook.sqlitedb", must be coped separately from chat messages database ("chat.db") from the source computer or iOS device, and **does not** contain message content—only contact metadata (names, phone numbers, emails, labels, etc.). 

All example values below are *synthetic* (e.g., “Jane Doe”, “555-123-4567”) and are provided solely to clarify how to read the schema.

## What the Tables Represent

| Table | Purpose |
| --- | --- |
| `ABPerson` | Primary contact table. One row per person, with name fields (`First`, `Last`, `DisplayName`, etc.), image metadata, timestamps, and a unique `ROWID`. |
| `ABMultiValue` | Stores all multi-valued attributes (phone numbers, emails, IM handles). Each row links back to `ABPerson` via `record_id` and records what kind of value it is (`property`), an optional `label`, and the actual `value` string. |
| `ABMultiValueLabel` | Lookup table for the textual label names (e.g., “home”, “work”) referenced from `ABMultiValue.label`. |
| `ABMultiValueEntry` | Maps numeric label identifiers to localized strings. Use this table when the numeric `label` column in `ABMultiValue` is not human-readable. |
| `ABGroup`, `ABGroupMembers` | Groups (e.g., “Family”) and the membership relations to people. |
| `ABPhoneLastFour` | Quick-lookup helper for the last four digits of phone numbers; useful for indexing or fuzzy matches. |
| `ABStore`, `ABAccount` | Metadata about the source/store (e.g., “On My Mac”, iCloud, CardDAV) of each contact. |

There are additional auxiliary tables such as `ABPersonFullTextSearch*`, `ABPersonChanges`, and `ABPersonLinked`, but the tables above are sufficient for reconciling phone numbers to names.

## How to Resolve Phone Numbers to Names

1. **Join `ABPerson` with `ABMultiValue`** using `ABPerson.ROWID = ABMultiValue.record_id`. Each `ABMultiValue` row records one contact point.
2. **Filter by `property`** to target different types of values:
   * `property = 3` → Phone numbers (most useful for Messages exports)
   * `property = 4` → Email addresses
   * `property = 5` → Instant-messaging handles
3. **Use `ABMultiValue.value`** to retrieve the raw string (e.g., `"+1 (555) 123-4567"`).
4. **Optional:** Use `ABMultiValue.label` (and `ABMultiValueEntry`) to interpret labels such as “work” or “mobile”.
5. Build a lookup map keyed by normalized phone numbers and use it to annotate message handles from `chat.db`. If a phone number already appears in the messages database, it can now be replaced with the corresponding first/last name from `ABPerson`.

### Sample Query (synthetic values)
```sql
SELECT
  ABPerson.First || ' ' || ABPerson.Last AS contact_name,
  ABMultiValue.value AS phone_number,
  ABMultiValueEntry.value AS label
FROM ABPerson
JOIN ABMultiValue
  ON ABPerson.ROWID = ABMultiValue.record_id
LEFT JOIN ABMultiValueEntry
  ON ABMultiValueEntry.parent_id = ABMultiValue.record_id
  AND ABMultiValueEntry.key = ABMultiValue.label
WHERE ABMultiValue.property = 3
  AND ABPerson.ROWID = 42;
```
_Example result:_ `("Jane Doe", "555-123-4567", "mobile")`

## Key Interpretation Notes

- `ABPerson` rows may have empty `First`/`Last` if there is a company-only contact; look instead at `DisplayName` or `Organization`.  
- Phone numbers are stored in the `value` column exactly as entered. Normalize them (strip punctuation, enforce country codes) before matching against `chat.db` handles.  
- Labels in `ABMultiValue.label` may be numeric indices. The `ABMultiValueEntry` table maps those indices (`parent_id`, `key`) back to their text equivalents.  
- The `ABPhoneLastFour` table contains `last_four` and `display_name` columns; it duplicates some of the phone-to-name information to speed up lookups, but it is not authoritative by itself.  
- If the backup includes multiple sources (e.g., iCloud + “On My Mac”), filters on `ABPerson.StoreID` or `ABStore` may help isolate the desired subset of contacts.

## Practical Usage

To enrich exported data:
1. Parse `AddressBook.sqlitedb` to build a dictionary from phone numbers → contact names.
2. When processing the Messages `chat.db`, normalize each handle (strip formatting, optional `+1` prefix) and look it up in the dictionary.  
3. If a name exists, annotate the exported HTML/text with that name; otherwise, fall back to the raw number.  

This approach lets you label every conversation with a human-friendly name exactly as macOS would display it, even though the original messages database only stores phone numbers/emails.
