"""Official help for the person receiving a letter: links to the sender's own pages about it.

Nemotron turns the answer key into a short web search (only the sender and the kind of letter,
never names, numbers or addresses), then Tavily searches the web, first on the sender's own site.
"""
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

import run_test as rt

TAVILY_URL = "https://api.tavily.com/search"

QUERY_SYSTEM = """You help someone who received an official letter find the sender's own web pages about it.

From the letter's title, summary, contact and sender (and where it was published, when given), write ONE short web search (3 to 8 words) that would find the sender's official page explaining this kind of letter or what to do about it. Use only the organisation's name and the kind of letter or programme (for example "IRS CP12 notice", "Edusave Awards MOE Singapore"). Never include a person's name, a case or account number, an amount of money, an address or a date.

Write the search in the language of the sender's own website (usually the letter's language). Name the sender's country or city in the search when it helps (a school or ministry has namesakes in other countries). Also give the sender's official website domain if you are sure of it (for example "irs.gov", "moe.gov.sg"), else "".

Reply with JSON only: {"query": "...", "domain": "..."}"""

# a model can slip personal details into the search anyway: these never leave the server
PERSONAL = re.compile(r"^[\d.,/:-]{4,}$|[$€£@]|^Rp")  # long numbers and dates, money, emails (a notice's "CP504" stays)
# Searching the whole web turns up namesakes (another country's ministry, a school with the same
# name): from there, only sites that look official are kept.
OFFICIAL = re.compile(r"(^|\.)(gov|gouv|gob|go|lg|edu|sch|ac|nhs|govt|government|gc)\.|\.(gov|edu|int|mil)$")


def enabled():
    return bool(os.environ.get("TAVILY_API_KEY"))


def search_query(api, fact, sender=None):
    """{"query", "domain"} for the letter, from the answer key (title, summary, contact) and, for an
    example, its publisher; the search itself leaves out anything personal."""
    user = json.dumps({"title": fact.get("title", ""), "summary": fact.get("summary", ""),
                       "contact": (fact.get("facts") or {}).get("contact", ""), "language": fact.get("language", ""),
                       **(sender or {})}, ensure_ascii=False)
    try:
        out = rt.parse_json(api.chat(rt.GRADER_MODEL, QUERY_SYSTEM, user, 0.0, max_tokens=120))
    except (ValueError, RuntimeError):
        return None
    query = " ".join(str(out.get("query") or "").split())[:120]
    domain = str(out.get("domain") or "").strip().lower().removeprefix("https://").removeprefix("http://").split("/")[0]
    query = " ".join(w for w in query.split() if not PERSONAL.search(w))
    if len(query) < 4:
        return None
    return {"query": query, "domain": domain if re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", domain) else ""}


def tavily(query, domain=""):
    body = {"query": query, "search_depth": "basic", "max_results": 5}
    if domain:
        body["include_domains"] = [domain]
    req = urllib.request.Request(TAVILY_URL, data=json.dumps(body).encode(), method="POST", headers={
        "Authorization": f"Bearer {os.environ.get('TAVILY_API_KEY', '')}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r).get("results") or []


def official_help(api, fact, sender=None):
    """{"query", "links": [{"title", "url", "snippet"}]} or None when there's nothing to show."""
    if not enabled():
        return None
    q = search_query(api, fact, sender)
    if not q:
        return None
    try:
        # the sender's own site first; if that finds nothing, official-looking sites on the whole web
        results = tavily(q["query"], q["domain"]) if q["domain"] else []
        if not results:
            results = [r for r in tavily(q["query"]) if OFFICIAL.search(urllib.parse.urlsplit(str(r.get("url") or "")).hostname or "")]
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None
    links = []
    for r in results:
        url = str(r.get("url") or "")
        title = " ".join(str(r.get("title") or "").replace("#", " ").split()).strip(" |-:")
        if not url.startswith("https://") or any(l["url"] == url or (title and l["title"] == title[:120]) for l in links):
            continue
        snippet = " ".join(str(r.get("content") or "").split())
        links.append({"title": title[:120] or url,
                      "url": url, "snippet": snippet[:180] + ("…" if len(snippet) > 180 else "")})
    return {"query": q["query"], "links": links[:3]} if links else None
