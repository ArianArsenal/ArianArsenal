#!/usr/bin/env python3
"""Generate the profile's stats and top-languages cards as SVGs.

Requires GITHUB_TOKEN. Run from anywhere; output goes to ../assets.
"""
import json
import os
import urllib.request
from collections import Counter
from pathlib import Path
from xml.sax.saxutils import escape

LOGIN = "ArianArsenal"
ASSETS = Path(__file__).resolve().parent.parent / "assets"
TOP_LANGUAGES = 6

WIDTH, HEIGHT = 495, 195
BG, BORDER, TRACK = "#161b22", "#30363d", "#21262d"
TEXT, MUTED, FALLBACK_COLOR = "#e6edf3", "#8b949e", "#8b949e"
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


def graphql(token, after=None):
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": LOGIN, "after": after}}).encode(),
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
        user = graphql(token, after)
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


def card(title, body):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-label="{escape(title)}">
  <rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{HEIGHT - 1}" rx="10" fill="{BG}" stroke="{BORDER}"/>
  <g font-family="{FONT}">
    <text x="28" y="40" font-size="17" font-weight="600" fill="{TEXT}">{escape(title)}</text>
{body}
  </g>
</svg>
"""


def stats_card(stats):
    rows = []
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
    rows = []
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


def main():
    stats, languages, colors = fetch(os.environ["GITHUB_TOKEN"])
    ASSETS.mkdir(exist_ok=True)
    (ASSETS / "stats.svg").write_text(stats_card(stats), encoding="utf-8", newline="\n")
    (ASSETS / "languages.svg").write_text(languages_card(languages, colors), encoding="utf-8", newline="\n")
    for label, value in stats:
        print(f"{label}: {value}")
    print({name: size for name, size in languages.most_common()})


if __name__ == "__main__":
    main()
