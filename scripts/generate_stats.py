#!/usr/bin/env python3
"""Generate the profile's stats and top-languages cards as SVGs.

Requires GITHUB_TOKEN. Run from anywhere; output goes to ../assets.
"""
import json
import os
import urllib.request
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

LOGIN = "ArianArsenal"
ASSETS = Path(__file__).resolve().parent.parent / "assets"
TOP_LANGUAGES = 6

WIDTH, HEIGHT = 495, 195
BG, BORDER, TRACK = "#161b22", "#30363d", "#21262d"
TEXT, MUTED, FALLBACK_COLOR = "#e6edf3", "#8b949e", "#8b949e"
STREAK_COLOR = "#fb8c00"
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"

QUERY = """
query($login: String!, $after: String) {
  user(login: $login) {
    pullRequests { totalCount }
    contributionsCollection { contributionCalendar { totalContributions } }
    repositories(ownerAffiliations: OWNER, privacy: PUBLIC, isFork: false, first: 100, after: $after) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        stargazerCount
        languages(first: 20, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""

YEARS_QUERY = """
query($login: String!) {
  user(login: $login) { contributionsCollection { contributionYears } }
}
"""

DAYS_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar { weeks { contributionDays { date contributionCount } } }
    }
  }
}
"""


def graphql(token, query, **variables):
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": {"login": LOGIN, **variables}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if "errors" in payload:
        raise RuntimeError(payload["errors"])
    return payload["data"]["user"]


def fetch(token):
    stars, languages, colors, after = 0, Counter(), {}, None
    while True:
        user = graphql(token, QUERY, after=after)
        for repo in user["repositories"]["nodes"]:
            stars += repo["stargazerCount"]
            for edge in repo["languages"]["edges"]:
                languages[edge["node"]["name"]] += edge["size"]
                colors[edge["node"]["name"]] = edge["node"]["color"] or FALLBACK_COLOR
        page = user["repositories"]["pageInfo"]
        if not page["hasNextPage"]:
            break
        after = page["endCursor"]
    stats = [
        ("Contributions (last year)", user["contributionsCollection"]["contributionCalendar"]["totalContributions"]),
        ("Pull requests", user["pullRequests"]["totalCount"]),
        ("Original repositories", user["repositories"]["totalCount"]),
        ("Stars earned", stars),
    ]
    return stats, languages, colors


def fetch_days(token):
    """Return (date, contribution count) for each day of the user's history, oldest first."""
    user = graphql(token, YEARS_QUERY)
    now = datetime.now(timezone.utc)
    days = {}
    for year in user["contributionsCollection"]["contributionYears"]:
        end = min(datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc), now)
        variables = {"from": f"{year}-01-01T00:00:00Z", "to": end.strftime("%Y-%m-%dT%H:%M:%SZ")}
        collection = graphql(token, DAYS_QUERY, **variables)["contributionsCollection"]
        for week in collection["contributionCalendar"]["weeks"]:
            for day in week["contributionDays"]:
                days[date.fromisoformat(day["date"])] = day["contributionCount"]
    return sorted(days.items())


def compute_streaks(days):
    """Summarise daily counts. A quiet today doesn't end the current streak, since the day isn't over."""
    active = [day for day, count in days if count]
    longest = run = (0, None, None)
    for day, count in days:
        run = (run[0] + 1, run[1] or day, day) if count else (0, None, None)
        if run[0] > longest[0]:
            longest = run
    recent = days[:-1] if days and not days[-1][1] else days
    length = 0
    for _, count in reversed(recent):
        if not count:
            break
        length += 1
    return {
        "total": sum(count for _, count in days),
        "first": active[0] if active else None,
        "last": active[-1] if active else None,
        "current": (length, recent[-length][0], recent[-1][0]) if length else (0, None, None),
        "longest": longest,
    }


def format_date(day, today):
    text = f"{day:%b} {day.day}"
    return text if day.year == today.year else f"{text}, {day.year}"


def format_range(streak, today):
    length, start, end = streak
    if not length:
        return "None yet"
    if start == end:
        return format_date(start, today)
    return f"{format_date(start, today)} - {format_date(end, today)}"


def card(title, body, width=WIDTH, height=HEIGHT):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">
  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="10" fill="{BG}" stroke="{BORDER}"/>
  <g font-family="{FONT}">
{body}
  </g>
</svg>
"""


def card_title(title):
    return f'    <text x="28" y="40" font-size="17" font-weight="600" fill="{TEXT}">{escape(title)}</text>'


def stats_card(stats):
    rows = [card_title("GitHub stats")]
    for i, (label, value) in enumerate(stats):
        y = 78 + i * 31
        rows.append(f'    <text x="28" y="{y}" font-size="14" fill="{MUTED}">{escape(label)}</text>')
        rows.append(
            f'    <text x="{WIDTH - 28}" y="{y}" font-size="16" font-weight="600" fill="{TEXT}" '
            f'text-anchor="end">{value:,}</text>'
        )
    return card("GitHub stats", "\n".join(rows))


def languages_card(languages, colors):
    total = sum(languages.values())
    bar_x, bar_width = 130, 285
    rows = [card_title("Top languages")]
    for i, (name, size) in enumerate(languages.most_common(TOP_LANGUAGES)):
        y = 68 + i * 21
        share = size / total
        rows.append(f'    <text x="28" y="{y}" font-size="13" fill="{MUTED}">{escape(name)}</text>')
        rows.append(f'    <rect x="{bar_x}" y="{y - 9}" width="{bar_width}" height="8" rx="4" fill="{TRACK}"/>')
        rows.append(
            f'    <rect x="{bar_x}" y="{y - 9}" width="{max(share * bar_width, 8):.1f}" height="8" rx="4" fill="{colors[name]}"/>'
        )
        rows.append(
            f'    <text x="{WIDTH - 28}" y="{y}" font-size="13" fill="{TEXT}" text-anchor="end">{share:.0%}</text>'
        )
    return card("Top languages", "\n".join(rows))


def streak_column(x, value, label, detail):
    return (
        f'    <text x="{x}" y="76" font-size="36" font-weight="700" fill="{TEXT}" text-anchor="middle">{value:,}</text>\n'
        f'    <text x="{x}" y="116" font-size="16" fill="{TEXT}" text-anchor="middle">{label}</text>\n'
        f'    <text x="{x}" y="146" font-size="13" fill="{MUTED}" text-anchor="middle">{escape(detail)}</text>'
    )


def streak_card(streaks, today):
    length = streaks["current"][0]
    if length:
        current_detail = format_range(streaks["current"], today)
    elif streaks["last"]:
        current_detail = f"Last active {format_date(streaks['last'], today)}"
    else:
        current_detail = "No activity yet"
    first = streaks["first"]
    since = f"{first:%b} {first.day}, {first.year} - Present" if first else "No activity yet"
    body = "\n".join([
        streak_column(135, streaks["total"], "Total Contributions", since),
        f'    <path d="M270 28V152M540 28V152" stroke="{BORDER}"/>',
        f'    <circle cx="405" cy="66" r="36" fill="none" stroke="{STREAK_COLOR}" stroke-width="5"/>',
        f'    <circle cx="405" cy="30" r="13" fill="{BG}"/>',
        f'    <path d="M405 17c2 5 8 8 8 15a8 8 0 0 1-16 0c0-3 1-5 3-7 0 3 1 4 3 4 1-4 0-8 2-12z" fill="{STREAK_COLOR}"/>',
        f'    <text x="405" y="77" font-size="30" font-weight="700" fill="{TEXT}" text-anchor="middle">{length:,}</text>',
        f'    <text x="405" y="130" font-size="16" font-weight="600" fill="{STREAK_COLOR}" text-anchor="middle">Current Streak</text>',
        f'    <text x="405" y="155" font-size="13" fill="{MUTED}" text-anchor="middle">{escape(current_detail)}</text>',
        streak_column(675, streaks["longest"][0], "Longest Streak", format_range(streaks["longest"], today)),
    ])
    return card("Contribution streak", body, 810, 180)


def main():
    token = os.environ["GITHUB_TOKEN"]
    stats, languages, colors = fetch(token)
    streaks = compute_streaks(fetch_days(token))
    today = datetime.now(timezone.utc).date()
    ASSETS.mkdir(exist_ok=True)
    (ASSETS / "stats.svg").write_text(stats_card(stats), encoding="utf-8", newline="\n")
    (ASSETS / "languages.svg").write_text(languages_card(languages, colors), encoding="utf-8", newline="\n")
    (ASSETS / "streak.svg").write_text(streak_card(streaks, today), encoding="utf-8", newline="\n")
    for label, value in stats:
        print(f"{label}: {value}")
    print({name: size for name, size in languages.most_common()})
    print(streaks)


if __name__ == "__main__":
    main()
