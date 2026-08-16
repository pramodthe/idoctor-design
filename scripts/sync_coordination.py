#!/usr/bin/env python3
"""Compile GitHub issues into the living coordination document.

GitHub issues are the source of truth. This script reads them and writes a
single dashboard (COORDINATION.md and/or a pinned issue labeled `coordination`).

Usage:
  python scripts/sync_coordination.py
  python scripts/sync_coordination.py --publish
  python scripts/sync_coordination.py --print
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO / "COORDINATION.md"
COORDINATION_LABEL = "coordination"
SKIP_LABELS = {COORDINATION_LABEL}
MARKER = "<!-- idoctor-coordination:auto -->"
FINGERPRINT_START = "<!-- idoctor-coordination:fingerprint:"
FINGERPRINT_END = " -->"

WORKSTREAMS: list[tuple[str, str]] = [
    ("ws1", "Workstream 1 — Scientific lead"),
    ("ws2", "Workstream 2–3 — Paperclip evidence"),
    ("ws4", "Workstream 4 — Proto design"),
    ("ws5", "Workstream 5 — Tamarind structures"),
    ("ws6", "Workstream 6 — Physics control"),
    ("ws7", "Workstream 7 — Critic + LangGraph"),
    ("ws8", "Workstream 8 — Trust UI"),
    ("ws9", "Workstream 9 — Eval + novelty"),
    ("ws10", "Workstream 10 — Demo + recording"),
]
WORKSTREAM_LABELS = {key for key, _ in WORKSTREAMS}


def _run_gh(args: list[str], *, input_text: str | None = None) -> str:
    env = os.environ.copy()
    env.setdefault("GH_PROMPT_DISABLED", "1")
    result = subprocess.run(
        ["gh", *args],
        check=False,
        capture_output=True,
        text=True,
        input=input_text,
        env=env,
        cwd=REPO,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "gh failed").strip()
        raise RuntimeError(f"gh {' '.join(args)} failed: {err}")
    return result.stdout


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _stamp(value: str | None) -> str:
    dt = _parse_dt(value)
    if dt is None:
        return "unknown"
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def _labels(issue: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for label in issue.get("labels") or []:
        if isinstance(label, dict):
            name = str(label.get("name") or "").strip()
        else:
            name = str(label).strip()
        if name:
            names.append(name)
    return names


def _assignees(issue: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for person in issue.get("assignees") or []:
        if isinstance(person, dict):
            login = str(person.get("login") or "").strip()
        else:
            login = str(person).strip()
        if login:
            names.append(login)
    return names


def _has_label(issue: dict[str, Any], name: str) -> bool:
    return name.lower() in {label.lower() for label in _labels(issue)}


def fetch_issues() -> list[dict[str, Any]]:
    raw = _run_gh(
        [
            "issue",
            "list",
            "--state",
            "all",
            "--limit",
            "200",
            "--json",
            "number,title,state,labels,assignees,updatedAt,createdAt,closedAt,url,body",
        ]
    )
    issues = json.loads(raw or "[]")
    if not isinstance(issues, list):
        raise RuntimeError("unexpected gh issue list payload")
    return issues


def _issue_line(issue: dict[str, Any]) -> str:
    number = issue.get("number")
    title = (issue.get("title") or "").strip() or "(no title)"
    url = issue.get("url") or f"#{number}"
    people = _assignees(issue)
    who = " ".join(f"@{name}" for name in people) if people else "_unassigned_"
    extra = [label for label in _labels(issue) if label not in WORKSTREAM_LABELS and label not in SKIP_LABELS]
    extra_s = f" `{ '`, `'.join(extra) }`" if extra else ""
    return f"- [#{number}]({url}) {title} — {who}{extra_s} · updated {_stamp(issue.get('updatedAt'))}"


def _excerpt(body: str | None, limit: int = 140) -> str:
    text = (body or "").strip()
    if text.startswith(MARKER):
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("<!-")]
    if not lines:
        return ""
    snippet = lines[0]
    if len(snippet) > limit:
        return snippet[: limit - 1] + "…"
    return snippet


def fingerprint_body(markdown: str) -> str:
    lines = [
        line
        for line in markdown.splitlines()
        if not line.startswith("_Last sync:") and FINGERPRINT_START not in line
    ]
    digest = hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()[:16]
    return digest


def render(issues: list[dict[str, Any]], *, now: datetime | None = None) -> str:
    now = now or _now_utc()
    work = [
        issue
        for issue in issues
        if not any(label.lower() in SKIP_LABELS for label in _labels(issue))
    ]
    open_issues = [issue for issue in work if str(issue.get("state", "")).upper() == "OPEN"]
    closed_issues = [issue for issue in work if str(issue.get("state", "")).upper() == "CLOSED"]
    blockers = [issue for issue in open_issues if _has_label(issue, "blocker")]
    decisions = [issue for issue in open_issues if _has_label(issue, "decision")]
    blocked = [issue for issue in open_issues if _has_label(issue, "blocked")]
    unassigned = [issue for issue in open_issues if not _assignees(issue)]
    recent_closed = []
    for issue in closed_issues:
        closed_at = _parse_dt(issue.get("closedAt"))
        if closed_at and (now - closed_at).total_seconds() <= 48 * 3600:
            recent_closed.append(issue)

    def by_number(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(items, key=lambda item: int(item.get("number") or 0))

    lines: list[str] = [
        MARKER,
        "# iDoctor Design — Coordination",
        "",
        "GitHub **issues are the coordination document.** This page is a generated snapshot.",
        "Open an issue to add work. Assign yourself to take it. Close it when the acceptance note is true.",
        "",
        f"_Last sync: {now.strftime('%Y-%m-%d %H:%M')} UTC_",
        "",
        "## Snapshot",
        "",
        "| Open | Blockers | Blocked | Unassigned | Closed (48h) |",
        "|---|---|---|---|---|",
        f"| {len(open_issues)} | {len(blockers)} | {len(blocked)} | {len(unassigned)} | {len(recent_closed)} |",
        "",
        "## How we coordinate",
        "",
        "1. Use an issue template: **Workstream**, **Blocker**, or **Decision**.",
        "2. Label with `ws1`…`ws10` (and `blocker` / `decision` / `blocked` as needed).",
        "3. Assign yourself when you start. Comment status, do not start a parallel doc.",
        "4. Close only when the acceptance note is true. Fixture fallback is allowed.",
        "5. A cron job rebuilds this dashboard every 15 minutes and on every issue change.",
        "",
        "Weekend checklist (frozen original): [`spec/TODO.md`](spec/TODO.md).",
        "",
    ]

    lines.extend(["## Blockers", ""])
    if blockers:
        for issue in by_number(blockers):
            lines.append(_issue_line(issue))
            excerpt = _excerpt(issue.get("body"))
            if excerpt:
                lines.append(f"  - {excerpt}")
        lines.append("")
    else:
        lines.extend(["_None open._", ""])

    lines.extend(["## Open work", ""])
    assigned_to_stream: set[int] = set()
    if open_issues:
        for key, heading in WORKSTREAMS:
            group = [issue for issue in by_number(open_issues) if _has_label(issue, key)]
            if not group:
                continue
            lines.append(f"### {heading}")
            lines.append("")
            for issue in group:
                assigned_to_stream.add(int(issue.get("number") or 0))
                lines.append(_issue_line(issue))
            lines.append("")
        leftover = [
            issue
            for issue in by_number(open_issues)
            if int(issue.get("number") or 0) not in assigned_to_stream
            and not _has_label(issue, "blocker")
            and not _has_label(issue, "decision")
        ]
        if leftover:
            lines.extend(["### Unlabeled / other", ""])
            for issue in leftover:
                lines.append(_issue_line(issue))
            lines.append("")
    else:
        lines.extend(["_No open work issues. Open one from the templates._", ""])

    open_decisions = [issue for issue in by_number(decisions)]
    lines.extend(["## Open decisions", ""])
    if open_decisions:
        for issue in open_decisions:
            lines.append(_issue_line(issue))
        lines.append("")
    else:
        lines.extend(["_None open._", ""])

    lines.extend(["## Recently closed", ""])
    if recent_closed:
        for issue in by_number(recent_closed):
            lines.append(_issue_line(issue))
        lines.append("")
    else:
        lines.extend(["_Nothing closed in the last 48 hours._", ""])

    lines.extend(
        [
            "---",
            "",
            "Do not paste secrets into issues. Generated by `scripts/sync_coordination.py`.",
            "",
        ]
    )
    body = "\n".join(lines)
    digest = fingerprint_body(body)
    stamped = body.replace(
        f"_Last sync: {now.strftime('%Y-%m-%d %H:%M')} UTC_",
        f"_Last sync: {now.strftime('%Y-%m-%d %H:%M')} UTC_\n{FINGERPRINT_START}{digest}{FINGERPRINT_END}",
        1,
    )
    return stamped


def read_existing_fingerprint(path: Path) -> str | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    return _extract_fingerprint(text)


def _extract_fingerprint(text: str) -> str | None:
    start = text.find(FINGERPRINT_START)
    if start < 0:
        return fingerprint_body(text)
    rest = text[start + len(FINGERPRINT_START) :]
    end = rest.find(FINGERPRINT_END)
    if end < 0:
        return fingerprint_body(text)
    return rest[:end]


def find_coordination_issue(issues: list[dict[str, Any]]) -> dict[str, Any] | None:
    open_coord = [
        issue
        for issue in issues
        if str(issue.get("state", "")).upper() == "OPEN" and _has_label(issue, COORDINATION_LABEL)
    ]
    if open_coord:
        return sorted(open_coord, key=lambda item: int(item.get("number") or 0))[0]
    return None


def publish_issue(markdown: str, issues: list[dict[str, Any]]) -> int:
    existing = find_coordination_issue(issues)
    title = "Coordination"
    if existing:
        number = int(existing["number"])
        old = existing.get("body") or ""
        if _extract_fingerprint(old) == _extract_fingerprint(markdown):
            print(f"coordination issue #{number} already current")
            return number
        _run_gh(["issue", "edit", str(number), "--title", title, "--body-file", "-"], input_text=markdown)
        print(f"updated coordination issue #{number}")
        return number
    created = _run_gh(
        [
            "issue",
            "create",
            "--title",
            title,
            "--label",
            COORDINATION_LABEL,
            "--body-file",
            "-",
        ],
        input_text=markdown,
    )
    print(created.strip())
    number_line = created.strip().rsplit("/", 1)[-1]
    try:
        number = int(number_line)
    except ValueError:
        return 0
    try:
        _run_gh(["issue", "pin", str(number)])
    except RuntimeError as exc:
        print(f"could not pin #{number}: {exc}", file=sys.stderr)
    return number


def write_if_changed(path: Path, markdown: str) -> bool:
    new_fp = _extract_fingerprint(markdown)
    old_fp = read_existing_fingerprint(path)
    if old_fp == new_fp and path.exists():
        print(f"{path.name} already current")
        return False
    path.write_text(markdown, encoding="utf-8")
    print(f"wrote {path}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync GitHub issues into the coordination document.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Markdown snapshot path")
    parser.add_argument("--publish", action="store_true", help="Update/create the pinned coordination issue")
    parser.add_argument("--print", action="store_true", dest="print_only", help="Print markdown and exit")
    parser.add_argument("--dry-run", action="store_true", help="Do not write files or publish")
    args = parser.parse_args()

    issues = fetch_issues()
    markdown = render(issues)

    if args.print_only or args.dry_run:
        sys.stdout.write(markdown)
        if not markdown.endswith("\n"):
            sys.stdout.write("\n")
        return 0

    write_if_changed(args.output, markdown)
    if args.publish:
        publish_issue(markdown, issues)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
