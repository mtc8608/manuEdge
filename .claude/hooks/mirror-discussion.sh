#!/usr/bin/env bash
#
# mirror-discussion.sh — Stop hook.
#
# Mirrors each Claude Code turn (the user prompt + Claude's final response) into
# .claude/discussion-log.md so the project discussion is captured in the repo and
# shared with the team. Reads the session transcript handed to it on stdin.
#
# Wired up in .claude/settings.json under hooks.Stop. Runs on every Stop event,
# but de-dupes on the last assistant message UUID so repeated Stops (e.g. /clear,
# resume, compact) don't append the same turn twice.
#
# Note: this is a deterministic mirror, not a semantic filter — it cannot decide
# what is "relevant". It logs the latest exchange verbatim. Prune the log by hand
# if needed. Turns triggered by a skill/slash-command may capture the expanded
# command text as the "user" line.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG="$ROOT/.claude/discussion-log.md"
STATE="$ROOT/.claude/hooks/.last-mirrored"

command -v jq >/dev/null 2>&1 || exit 0

payload="$(cat)"
transcript="$(printf '%s' "$payload" | jq -r '.transcript_path // empty')"
[ -n "$transcript" ] && [ -f "$transcript" ] || exit 0

# UUID of the most recent assistant message that contains visible text.
last_uuid="$(jq -rs '
  [ .[] | select(.type=="assistant")
        | select(any(.message.content[]?; .type=="text")) ]
  | last | .uuid // empty' "$transcript")"
[ -n "$last_uuid" ] || exit 0

# Already mirrored this turn? Nothing to do.
[ -f "$STATE" ] && [ "$(cat "$STATE")" = "$last_uuid" ] && exit 0

# Claude's final text response for this turn (text blocks of the last assistant msg).
assistant_text="$(jq -rs '
  [ .[] | select(.type=="assistant")
        | select(any(.message.content[]?; .type=="text")) ]
  | last | .message.content[] | select(.type=="text") | .text' "$transcript")"
[ -n "$assistant_text" ] || exit 0

# Best-effort: the user prompt that drove this turn — last externally-typed text
# that isn't an injected <tag> context block.
user_text="$(jq -rs '
  [ .[] | select(.type=="user" and .userType=="external")
        | .message.content[]? | select(.type=="text") | .text
        | select(startswith("<") | not) ]
  | last // empty' "$transcript")"

ts="$(jq -rs 'last.timestamp // empty' "$transcript")"

{
  printf '\n## %s\n\n' "${ts:-entry}"
  [ -n "$user_text" ] && printf '**User:** %s\n\n' "$user_text"
  printf '**Claude:**\n\n%s\n' "$assistant_text"
  printf '\n<!-- mirrored:%s -->\n' "$last_uuid"
} >> "$LOG"

printf '%s' "$last_uuid" > "$STATE"
exit 0
