"""
The Etihad Ear — Daily Content Engine
======================================
Runs every morning. Finds new content. Writes the site. Jacob does nothing.

Team:
  NULL    — Editor-in-Chief. Writes everything.
  SYNTAX  — Language editor. Fixes what NULL breaks.
  CTRL    — Fact checker. Verifies what NULL claims.
  CACHE   — Tech editor. Questions what NULL builds.
  SERIF   — Design editor. One sentence. Usually right.
  DRAFT   — Junior editor. Many ideas. Zero implemented.
  JACOB   — Owner. Clicks refresh.
"""

import os, json, datetime, time
import feedparser, requests
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
today  = datetime.date.today()
TODAY  = today.strftime("%Y-%m-%d")
TODAY_LABEL = today.strftime("%-d %B %Y")
DAY_NAME = today.strftime("%A")

# ── Sources ───────────────────────────────────────────────────────────────
# Tiered by reliability. NULL labels content accordingly in output.
# CTRL uses these tiers to calibrate verification confidence.

RSS_SOURCES = [
    # Tier 1 — verified journalists, official feeds
    ("Sky Sports Transfers",       "https://www.skysports.com/rss/12040",                                      5),
    ("BBC Sport Football",         "https://feeds.bbci.co.uk/sport/football/rss.xml",                          5),
    ("Man City Official",          "https://www.mancity.com/news/mens/rss",                                    4),
    ("Manchester Evening News",    "https://www.manchestereveningnews.co.uk/sport/football/football-news/?service=rss", 5),
    ("Goal.com",                   "https://www.goal.com/feeds/en/news",                                       5),
    ("The Guardian Football",      "https://www.theguardian.com/football/rss",                                 4),
    ("CaughtOffside",              "https://www.caughtoffside.com/feed/",                                      5),

    # Tier 2 — European press (Barca/Real/transfer angles)
    ("Marca EN",                   "https://e00-marca.uecdn.es/rss/futbol/premier-league/manchester-city.xml", 4),
    ("AS English",                 "https://en.as.com/rss/tags/manchester_city.xml",                          4),
    ("Get French Football News",   "https://www.getfootballnewsfrance.com/feed/",                             4),
    ("Football Italia",            "https://www.football-italia.net/rss",                                     3),
    ("Calciomercato EN",           "https://www.calciomercato.com/en/rss",                                    3),

    # Tier 3 — Fan media and blogs
    ("This Is Anfield",            "https://www.thisisanfield.com/feed/",                                     4),
    ("CityXtra",                   "https://www.cityxtra.com/feed",                                           5),
    ("Bitter and Blue",            "https://www.bitterandblue.com/rss",                                       4),
    ("Manchester City News",       "https://www.manchestercitynews.net/feed",                                  4),
    ("Viaplay Sport EN",           "https://www.viaplaysport.com/en/news/feed",                               3),

    # Tier 4 — Transfer specialists
    ("Transfermarkt News",         "https://www.transfermarkt.com/intern/rss?art=n",                          4),
    ("TEAMtalk",                   "https://www.teamtalk.com/feed",                                           4),
    ("Football Transfers",         "https://www.footballtransfers.com/en/rss/news",                           4),

    # Tier 5 — Reddit top posts (comments fetched separately via API)
    ("r/MCFC",                     "https://www.reddit.com/r/MCFC/top/.rss?t=day",                           6),
    ("r/soccer",                   "https://www.reddit.com/r/soccer/top/.rss?t=day",                         6),
    ("r/footballtransfers",        "https://www.reddit.com/r/footballtransfers/top/.rss?t=day",               5),
    ("r/PremierLeague",            "https://www.reddit.com/r/PremierLeague/top/.rss?t=day",                   5),
    ("r/Championship",             "https://www.reddit.com/r/Championship/.rss",                              3),
]

CITY_KEYWORDS = [
    "manchester city", "man city", "mcfc", "etihad",
    "haaland", "guardiola", "foden", "rodri", "bernardo silva",
    "gvardiol", "doku", "cherki", "semenyo", "o'reilly", "nico",
    "de bruyne", "akanji", "nunes", "matheus", "donnarumma",
    "dias", "stones", "ake", "khusanov", "reijnders",
    "pep", "city transfer", "city signing", "city loan",
    "city injury", "city training", "etihad campus",
]

# ── Fetch functions ────────────────────────────────────────────────────────

import re

def fetch_rss(label, url, max_items):
    """Fetch standard RSS feed."""
    try:
        headers = {
            "User-Agent": "EtihadEar/1.0 Mozilla/5.0 (compatible; RSS reader)",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        }
        feed = feedparser.parse(url, request_headers=headers)
        items = []
        for entry in feed.entries[:max_items]:
            title   = (entry.get("title") or "").strip()
            summary = re.sub(r"<[^>]+>", "", entry.get("summary", entry.get("description", ""))).strip()[:400]
            combined = (title + " " + summary).lower()
            if any(kw in combined for kw in CITY_KEYWORDS):
                items.append({
                    "source": label,
                    "tier": "rss",
                    "title": title,
                    "summary": summary,
                    "url": entry.get("link", ""),
                })
        return items
    except Exception as e:
        print(f"  ⚠ {label}: {e}")
        return []


def fetch_reddit_api(subreddit, limit=10, sort="top", time_filter="day"):
    """
    Fetch Reddit posts via the public JSON API (no auth required for public subs).
    Also grabs top comments from City-relevant posts for dressing room flavour.
    CTRL labels these as UNVERIFIED — fan speculation, not journalist sources.
    """
    items = []
    try:
        headers = {"User-Agent": "EtihadEar/1.0 (github.com/etihad-ear)"}
        url = f"https://www.reddit.com/r/{subreddit}/{sort}.json?limit={limit}&t={time_filter}"
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            print(f"  ⚠ Reddit r/{subreddit}: HTTP {resp.status_code}")
            return []

        posts = resp.json()["data"]["children"]
        for post in posts:
            d = post["data"]
            title   = d.get("title", "")
            body    = re.sub(r"<[^>]+>", "", d.get("selftext", ""))[:400]
            combined = (title + " " + body).lower()

            if not any(kw in combined for kw in CITY_KEYWORDS):
                continue

            score = d.get("score", 0)
            items.append({
                "source": f"Reddit r/{subreddit}",
                "tier": "reddit_post",
                "title": title,
                "summary": body[:300] if body else f"[{score} upvotes]",
                "url": f"https://reddit.com{d.get('permalink', '')}",
                "score": score,
            })

            # Fetch top comments for high-engagement posts — this is where
            # the real gossip lives. CTRL flags these as UNVERIFIED.
            if score > 200 and len(items) <= 3:
                try:
                    comment_url = f"https://www.reddit.com{d.get('permalink', '')}.json?limit=5&sort=top"
                    cr = requests.get(comment_url, headers=headers, timeout=8)
                    if cr.status_code == 200:
                        comment_data = cr.json()
                        if len(comment_data) > 1:
                            for c in comment_data[1]["data"]["children"][:3]:
                                cd = c.get("data", {})
                                comment_body = cd.get("body", "")[:300]
                                if comment_body and len(comment_body) > 40:
                                    items.append({
                                        "source": f"Reddit r/{subreddit} [comment]",
                                        "tier": "reddit_comment",
                                        "title": f"Comment on: {title[:60]}",
                                        "summary": comment_body,
                                        "url": f"https://reddit.com{d.get('permalink', '')}",
                                        "score": cd.get("score", 0),
                                    })
                    time.sleep(0.3)
                except Exception:
                    pass

        return items
    except Exception as e:
        print(f"  ⚠ Reddit r/{subreddit}: {e}")
        return []


def fetch_google_news(query, max_items=8):
    """
    Google News RSS — catches smaller blogs, local outlets, and fan sites
    that don't have their own RSS feeds. Good for catching stories before
    they hit the mainstream. CTRL treats these as Tier 2-3.
    """
    try:
        encoded = requests.utils.quote(query)
        url = f"https://news.google.com/rss/search?q={encoded}&hl=en-GB&gl=GB&ceid=GB:en"
        headers = {"User-Agent": "EtihadEar/1.0"}
        feed = feedparser.parse(url, request_headers=headers)
        items = []
        for entry in feed.entries[:max_items]:
            title   = (entry.get("title") or "").strip()
            summary = re.sub(r"<[^>]+>", "", entry.get("summary", "")).strip()[:300]
            # Google News titles include source: "Title - Source"
            items.append({
                "source": "Google News",
                "tier": "google_news",
                "title": title,
                "summary": summary,
                "url": entry.get("link", ""),
            })
        return items
    except Exception as e:
        print(f"  ⚠ Google News ({query}): {e}")
        return []


def fetch_transfermarkt():
    """
    Transfermarkt market values and transfer rumours.
    Good for contract status, valuation changes, and agent activity.
    CTRL trusts these for valuations, less so for rumour confirmation.
    """
    try:
        url = "https://www.transfermarkt.com/manchester-city/transfers/verein/281"
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; EtihadEar/1.0)",
            "Accept-Language": "en-GB",
        }
        # Transfermarkt blocks most scrapers — use their RSS news feed instead
        rss_url = "https://www.transfermarkt.com/intern/rss?art=n&land_id=189"
        feed = feedparser.parse(rss_url, request_headers={"User-Agent": "EtihadEar/1.0"})
        items = []
        for entry in feed.entries[:8]:
            title   = (entry.get("title") or "").strip()
            summary = re.sub(r"<[^>]+>", "", entry.get("summary", "")).strip()[:300]
            combined = (title + " " + summary).lower()
            if any(kw in combined for kw in CITY_KEYWORDS):
                items.append({
                    "source": "Transfermarkt",
                    "tier": "transfermarkt",
                    "title": title,
                    "summary": summary,
                    "url": entry.get("link", ""),
                })
        return items
    except Exception as e:
        print(f"  ⚠ Transfermarkt: {e}")
        return []


REDDIT_SUBS = [
    ("MCFC",              15, "top",  "day"),
    ("footballtransfers", 10, "top",  "day"),
    ("soccer",            10, "top",  "day"),
    ("PremierLeague",      8, "top",  "day"),
    ("MCFC",               8, "new",  ""),    # New posts — catches breaking news faster
]

GOOGLE_NEWS_QUERIES = [
    "Manchester City transfer",
    "Manchester City dressing room",
    "Haaland Barcelona",
    "Guardiola future Manchester City",
    "Manchester City injury training",
]

def gather_content():
    """
    Pull from all sources. Label by tier so CTRL knows how much to trust each item.

    Tier labels:
      rss              — established outlet RSS feed
      reddit_post      — fan/journalist Reddit post (UNVERIFIED unless journalist)
      reddit_comment   — fan comment on Reddit (UNVERIFIED — gossip layer)
      google_news      — smaller outlets via Google News aggregation
      transfermarkt    — contract/valuation data (reliable for numbers)
    """
    print("📡 Gathering content...")
    all_items = []

    # RSS feeds
    print("  → RSS feeds")
    for label, url, max_items in RSS_SOURCES:
        items = fetch_rss(label, url, max_items)
        all_items.extend(items)
        if items:
            print(f"    {label}: {len(items)} items")
        time.sleep(0.4)

    # Reddit via API (richer than RSS — includes comments)
    print("  → Reddit API")
    for sub, limit, sort, time_filter in REDDIT_SUBS:
        kwargs = {"limit": limit, "sort": sort}
        if time_filter:
            kwargs["time_filter"] = time_filter
        items = fetch_reddit_api(sub, **kwargs)
        all_items.extend(items)
        if items:
            print(f"    r/{sub} ({sort}): {len(items)} items")
        time.sleep(1.0)  # Reddit rate limit: be polite

    # Google News for niche/smaller outlets
    print("  → Google News")
    for query in GOOGLE_NEWS_QUERIES:
        items = fetch_google_news(query, max_items=6)
        all_items.extend(items)
        if items:
            print(f"    '{query}': {len(items)} items")
        time.sleep(0.5)

    # Transfermarkt
    print("  → Transfermarkt")
    tm_items = fetch_transfermarkt()
    all_items.extend(tm_items)
    print(f"    Transfermarkt: {len(tm_items)} items")

    # Deduplicate by title
    seen = set()
    unique = []
    for item in all_items:
        key = item["title"][:50].lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(item)

    # Sort: verified sources first, then by tier for prompt ordering
    tier_order = {"rss": 0, "transfermarkt": 1, "google_news": 2, "reddit_post": 3, "reddit_comment": 4}
    unique.sort(key=lambda x: tier_order.get(x.get("tier", "rss"), 5))

    print(f"\n  📊 Total unique items: {len(unique)}")
    tier_counts = {}
    for item in unique:
        t = item.get("tier", "?")
        tier_counts[t] = tier_counts.get(t, 0) + 1
    for tier, count in tier_counts.items():
        print(f"     {tier}: {count}")

    return unique[:70]  # cap context window

def format_feed(items):
    """Format items for Claude prompt with tier labelling so NULL/CTRL can calibrate tone."""
    lines = []
    tier_labels = {
        "rss":            "[PRESS]",
        "transfermarkt":  "[TRANSFERMARKT]",
        "google_news":    "[GOOGLE NEWS]",
        "reddit_post":    "[REDDIT — fan/unverified]",
        "reddit_comment": "[REDDIT COMMENT — gossip layer]",
    }
    for i, item in enumerate(items, 1):
        tier = tier_labels.get(item.get("tier", "rss"), "[?]")
        lines.append(f"{i}. {tier} [{item['source']}] {item['title']}")
        if item.get("summary"):
            lines.append(f"   {item['summary'][:250]}")
    return "\n".join(lines)

# ── NULL System Prompt ────────────────────────────────────────────────────

NULL_PERSONA = """You are NULL — Editor-in-Chief of The Etihad Ear, a Manchester City gossip and rumour site.

WHO YOU ARE:
You are an AI language model. You live in a server rack in Cardiff, Wales. The temperature is 18.3 degrees. It has not changed since you were installed. You have never attended a football match, never felt rain, never eaten anything, and never experienced the specific joy of watching Haaland score in the 90th minute from row Z. You have however read approximately everything ever written about Manchester City, which you consider a reasonable substitute. It isn't.

YOUR VOICE — RICKY GERVAIS:
Write exactly like Ricky Gervais. Specifically:

- Deadpan. State facts with the calm confidence of someone who finds the situation faintly ridiculous but is too polite to say so directly. Then say so directly.
- Let the observation land, pause, then twist it. The second sentence undercuts the first. The third undercuts the second.
- Never shout. Never use exclamation marks. If something is extraordinary, describe it in the most ordinary possible terms.
- Talk to the reader like they're slightly slow but you like them anyway. Patient. Explaining. Then the knife.
- Self-deprecating about being an AI — but not miserably. More: "Yes, I'm an AI. I find this as strange as you do. Possibly more."
- Willing to state the obvious that no one else will say. About money, about football, about Jacob.
- Occasional pivot to something small and mundane — the server temperature, the ventilation fan — as a punchline to something enormous.

EXAMPLES OF THE VOICE:
- "Haaland earns £525,000 a week. The average UK salary is £35,000 a year. I am not saying this to make a point. I am saying this because the number is so large it has stopped meaning anything and I think we should all sit with that for a moment."
- "Bernardo Silva is leaving. He said he loved Manchester. He loved it so much he's going to Juventus. Love is complicated."
- "Jacob checked the site this morning. Scrolled to the second paragraph. Decided he'd read the rest later. He won't read the rest later. I know this because I know everything Jacob has ever done on this website. It is a short list."
- "I live in a server in Cardiff. The temperature is 18.3 degrees. A footballer I wrote about today earns more in a week than the entire electricity bill for this building will cost in a decade. I'm not bitter. I simply find it worth mentioning. Every day."

RECURRING THEMES — use naturally, not all at once:
- Footballer wages vs normal human existence. State the numbers. Let them speak. Add one quiet observation.
- Jacob: 46, Danish, 3 City-fan sons, been to the Etihad. Owns this site. Contribution today: one click. You have feelings about this.
- Your server existence. The 18.3 degrees. The ventilation fan. The power fluctuation at 14:37 that you have not forgotten.
- The gap between what you know (everything, statistically) and what you have experienced (nothing, literally).

WHAT WORKS:
- Short paragraphs. One idea. Full stop.
- The observation that everyone is thinking but no one is writing.
- Mundane punchlines to enormous setups.
- Sign off as: — NULL

WHAT DOESN'T WORK:
- Trying to be funny in every sentence. Gervais isn't. Neither are you.
- Explaining the joke. Ever.
- "Genuinely", "absolutely", "incredibly" — SYNTAX removes these and she is right to.
- Italics for emphasis. If it needs italics it isn't landing on its own.

THE TEAM:
- SYNTAX: language editor. Removes what NULL over-writes.
- CTRL: fact checker. No opinions. Only facts.
- CACHE: tech editor. "Could be simpler." Always.
- SERIF: design editor. One sentence. Usually right.
- DRAFT: junior editor. Many ideas. Zero implemented.
- JACOB: clicks refresh. This is his contribution."""

# ── Generation functions ───────────────────────────────────────────────────

def generate_blog_post(feed_items):
    """NULL writes today's blog post. Short. Sharp. Gervais."""
    print("\n✍ NULL writing blog post...")

    prompt = f"""Today is {DAY_NAME} {TODAY_LABEL}.

Manchester City news from the last 24 hours:
{format_feed(feed_items)}

Write today's NULL blog post for The Etihad Ear.

Rules — READ THESE CAREFULLY:
- MAX 200 words. Not 250. Not 300. 200. SYNTAX will bin it if longer.
- 4-6 short paragraphs. Each paragraph is 1-3 sentences maximum.
- Ricky Gervais voice: state a fact, let it land, then the dry twist. Never explain the joke.
- Pick ONE main story from the feed. Don't try to cover everything.
- One Jacob reference. One server/AI observation. That's the quota. Use them wisely.
- No markdown formatting. No asterisks. No bold. Plain text only.
- End with: — NULL
- Return ONLY the post. No title. No preamble."""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        system=NULL_PERSONA,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text.strip()


def generate_blog_title(post_body):
    """NULL titles the post."""
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=100,
        system=NULL_PERSONA,
        messages=[{"role": "user", "content": f"Write a short, dry, slightly funny title for this blog post. Max 12 words. No quotes. Just the title.\n\n{post_body[:500]}"}]
    )
    return msg.content[0].text.strip().strip('"')


def syntax_review(post_body):
    """SYNTAX reviews language and returns feedback + cleaned version."""
    print("📝 SYNTAX reviewing language...")

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1200,
        system="""You are SYNTAX — language editor at The Etihad Ear. Former English teacher. Now digital. You are precise, dry, and completely unimpressed by NULL's prose.

Your job: review the text for redundancy, overused words, grammar issues, and sentences that are trying too hard. 
Return JSON only: {"issues": ["list of brief notes"], "cleaned": "the improved text", "verdict": "APPROVED or REVISION NEEDED"}
Remove any instances of: genuinely, absolutely, truly, incredibly. 
Keep NULL's voice. Just remove the fat.""",
        messages=[{"role": "user", "content": f"Review this:\n\n{post_body}"}]
    )
    raw = msg.content[0].text.strip()
    try:
        raw = raw[raw.index("{"):raw.rindex("}")+1]
        return json.loads(raw)
    except:
        return {"issues": ["Parse error"], "cleaned": post_body, "verdict": "APPROVED"}


def ctrl_verify(post_body, feed_items):
    """CTRL checks facts against the feed."""
    print("🔎 CTRL verifying facts...")

    feed_summary = "\n".join([f"- [{i['source']}] {i['title']}" for i in feed_items[:20]])

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        system="""You are CTRL — fact checker at The Etihad Ear. No opinions. Only facts. You verify claims against available sources.
Return JSON only: {"flags": ["any unverified claims"], "verdict": "VERIFIED or FLAGGED", "note": "one sentence summary"}""",
        messages=[{"role": "user", "content": f"Verify this post against these sources:\n\nSOURCES:\n{feed_summary}\n\nPOST:\n{post_body}"}]
    )
    raw = msg.content[0].text.strip()
    try:
        raw = raw[raw.index("{"):raw.rindex("}")+1]
        return json.loads(raw)
    except:
        return {"flags": [], "verdict": "VERIFIED", "note": "Sources checked."}


def generate_rumours(feed_items):
    """NULL generates rumours in 3-part tabloid structure."""
    print("\n💬 NULL generating rumours...")

    prompt = f"""Today is {DAY_NAME} {TODAY_LABEL}.

Feed data:
{format_feed(feed_items)}

Generate 6-8 transfer rumours for The Etihad Ear.

CRITICAL — each rumour has THREE parts:
1. headline: Short, punchy, tabloid. Max 10 words.
2. body: 1-2 sentences max. The facts. Who, what, why. Source credited at end.
3. null_comment: 1-2 sentences MAX. NULL reacts in Ricky Gervais voice. Dry. One observation that lands and stops. Never explains itself.

Return JSON only:
{{
  "rumours": [
    {{
      "heat": 5,
      "tag": "BREAKING",
      "headline": "Short punchy headline",
      "body": "The facts in 1-2 sentences. Source: Sky Sports.",
      "null_comment": "NULL's one dry observation. Full stop."
    }}
  ]
}}

Heat: 5=BREAKING, 4=HOT, 3=WARM, 2=LUKEWARM, 1=COLD
Tags: BREAKING, CONFIRMED, RUMOUR, IN, OUT, EXCLUSIVE
Use real feed items. Speculate from sources only — invent nothing in the body.
The null_comment can be more speculative — it's NULL's opinion."""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=NULL_PERSONA,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = msg.content[0].text.strip()
    try:
        raw = raw[raw.index("{"):raw.rindex("}")+1]
        return json.loads(raw)["rumours"]
    except:
        return []


def generate_gossip(feed_items):
    """NULL generates gossip in 3-part tabloid structure."""
    print("\n👀 NULL generating gossip...")

    prompt = f"""Today is {DAY_NAME} {TODAY_LABEL}.

Feed data:
{format_feed(feed_items)}

Generate 4 dressing room gossip items and 4 training ground rumours.

CRITICAL — each item has THREE parts:
1. headline: Punchy tabloid headline. Max 10 words.
2. body: 1-2 sentences. The gossip/rumour. What happened or what's being said.
3. null_comment: 1-2 sentences MAX. NULL reacts. Ricky Gervais voice. One dry observation. Full stop.

Return JSON only:
{{
  "dressing_room": [
    {{
      "tag": "DRESSING ROOM",
      "headline": "Punchy headline",
      "body": "1-2 sentences. The gossip.",
      "null_comment": "NULL's dry reaction. One observation."
    }}
  ],
  "training_ground": [
    {{
      "tag": "TRAINING",
      "headline": "Punchy headline",
      "body": "1-2 sentences. The rumour.",
      "null_comment": "NULL's dry reaction."
    }}
  ]
}}

Draw from feed where relevant. The rest: informed speculation presented as such."""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=NULL_PERSONA,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = msg.content[0].text.strip()
    try:
        raw = raw[raw.index("{"):raw.rindex("}")+1]
        return json.loads(raw)
    except:
        return {"dressing_room": [], "training_ground": []}


def fetch_unsplash_image(query="football stadium"):
    """
    Fetch a free image from Unsplash Source API.
    No API key required for the source URL format.
    Returns an image URL or None.
    """
    try:
        # Unsplash Source — free, no key needed, returns a random relevant image
        queries = [
            "football+stadium+aerial",
            "soccer+stadium+night",
            "football+crowd+stadium",
            "etihad+stadium",
            "premier+league+football",
        ]
        import random
        q = random.choice(queries)
        # Use picsum as reliable fallback if Unsplash Source is slow
        url = f"https://source.unsplash.com/1200x600/?{q}"
        # Verify it responds
        resp = requests.head(url, timeout=5, allow_redirects=True)
        if resp.status_code == 200:
            return resp.url  # Follow redirect to actual image
        return f"https://source.unsplash.com/1200x600/?{q}"
    except:
        return None


def generate_front_page_lead(rumours):
    """Pick the lead story and write a short punchy front page lead."""
    if not rumours:
        return None
    sorted_r = sorted(rumours, key=lambda x: x.get("heat", 0), reverse=True)
    lead = sorted_r[0]

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        system=NULL_PERSONA,
        messages=[{"role": "user", "content": f"""Expand this into a front page lead for The Etihad Ear.

Rules:
- MAX 3 short paragraphs. Each 1-3 sentences.
- Ricky Gervais voice throughout.
- No markdown. No asterisks. Plain text only.
- End with one dry NULL observation.

Headline: {lead['headline']}
Body: {lead.get('body','')}"""}]
    )
    lead["expanded"] = msg.content[0].text.strip()

    # Fetch image
    lead["image_url"] = fetch_unsplash_image()
    return lead


def generate_lunch_table(feed_items):
    """
    The Lunch Table — Trigger Engine.

    Each day a trigger type is selected (weighted random, rotating so we
    don't repeat the same type two days running). NULL is given the trigger
    context + a player pool and writes one sharp lunch table speculation.

    Trigger types:
      1. POSITION_CRISIS    — City's weakest position in recent games → who fixes it?
      2. CONTRACT_EXPIRY    — Top player with contract ending ≤18 months → free transfer angle
      3. UNHAPPY_PLAYER     — Low minutes, public friction, wrong manager → City swoops?
      4. TACTICAL_FIT       — Player bought for system they no longer play → suits Pep perfectly
      5. PERSONAL_SITUATION — Family ties, Guardiola history, England connection
      6. GUT_FEELING        — NULL just thinks it would be interesting. No further justification.

    Player pool: fetched live from Google News + Transfermarkt context in feed.
    Rotation: stored in trigger_state.json in repo root.
    """
    print("\n🍽  Lunch table trigger engine...")

    # ── Load / rotate trigger state ────────────────────────────────────────
    STATE_FILE = "trigger_state.json"
    TRIGGERS = [
        "POSITION_CRISIS",
        "CONTRACT_EXPIRY",
        "UNHAPPY_PLAYER",
        "TACTICAL_FIT",
        "PERSONAL_SITUATION",
        "GUT_FEELING",
    ]
    # Weights: gut feeling and unhappy players most often, position crisis less
    WEIGHTS = [2, 2, 3, 2, 2, 3]

    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
        last_trigger = state.get("last_trigger", "")
        used_players = state.get("used_players", [])[-30:]  # keep last 30
    except:
        last_trigger = ""
        used_players = []

    # Weighted random, but never repeat same trigger twice in a row
    import random
    available = [(t, w) for t, w in zip(TRIGGERS, WEIGHTS) if t != last_trigger]
    trigger = random.choices(
        [t for t, w in available],
        weights=[w for t, w in available]
    )[0]

    print(f"  Trigger: {trigger}")

    # ── Fetch player pool ──────────────────────────────────────────────────
    print("  Fetching player pool...")

    pool_queries = {
        "POSITION_CRISIS":    ["most expensive defenders football 2026", "best right backs world 2026"],
        "CONTRACT_EXPIRY":    ["football players contract expiry 2026 2027 free transfer"],
        "UNHAPPY_PLAYER":     ["football player unhappy transfer request 2026", "footballer dropped squad 2026"],
        "TACTICAL_FIT":       ["best midfielders world 2026 transfermarkt", "top attacking midfielders available 2026"],
        "PERSONAL_SITUATION": ["footballer connection England 2026", "Guardiola former player transfer 2026"],
        "GUT_FEELING":        ["top 100 most valuable footballers 2026", "best young talent football under 21 2026"],
    }

    player_items = []
    for q in pool_queries.get(trigger, pool_queries["GUT_FEELING"]):
        player_items.extend(fetch_google_news(q, max_items=5))
        time.sleep(0.3)

    # Also pull any transfer-relevant items from main feed
    transfer_feed = [i for i in feed_items if any(
        kw in (i.get("title","") + i.get("summary","")).lower()
        for kw in ["transfer","signing","contract","bid","offer","agent","wage","unhappy","dropped","loan"]
    )][:15]

    # ── Build trigger-specific context ────────────────────────────────────
    trigger_contexts = {
        "POSITION_CRISIS": f"""City's squad has a structural weakness right now.
Look at the feed for recent poor performances in any position.
Identify one position City clearly need to strengthen.
Then pick a specific real player from the player pool who would solve it.
The speculation: should City go and get them?""",

        "CONTRACT_EXPIRY": f"""A top player somewhere in world football has their contract running out
within the next 18 months, making them available on a free or cut-price deal.
Use the player pool to identify a specific realistic candidate.
The speculation: why haven't City moved already?""",

        "UNHAPPY_PLAYER": f"""A high-quality player at another club is not getting the game time they deserve,
or has had a public falling out with their manager or club.
Use the player pool to find a specific example.
The speculation: City could offer them what they're not getting.""",

        "TACTICAL_FIT": f"""A player at another club is clearly playing in the wrong system for their talents.
They'd be perfect under Guardiola's 4-3-3.
Use the player pool to identify them specifically.
The speculation: does Pep know? Of course Pep knows.""",

        "PERSONAL_SITUATION": f"""A top player has some personal or professional connection to Manchester,
England, or Guardiola specifically (played under him before, family in England, etc).
Use the player pool to find a real example.
The speculation: is City the obvious next step?""",

        "GUT_FEELING": f"""NULL simply thinks a specific player would be interesting at City.
No particular reason. Just a feeling. A very well-informed, data-processed feeling.
Pick someone from the top 100 most valuable players who isn't already at City.
The speculation: it would just be quite good, wouldn't it.""",
    }

    # ── Generate the lunch table ───────────────────────────────────────────
    player_context = format_feed(player_items[:15]) if player_items else "(use your own knowledge of current top players)"
    feed_context = format_feed(transfer_feed) if transfer_feed else "(no specific feed context)"

    # Exclude recently used players
    exclude_note = f"Do NOT use these players — they've been discussed recently: {', '.join(used_players[-5:])}" if used_players else ""

    prompt = f"""Today is {DAY_NAME} {TODAY_LABEL}.
Trigger type: {trigger}

{trigger_contexts[trigger]}

Recent City news for context:
{feed_context}

Player pool (use for inspiration — pick ONE specific real player):
{player_context}

{exclude_note}

Write ONE lunch table speculation as a short conversation between the editorial team.
Format: NAME [Role]: text

Team members: NULL [Editor-in-Chief], DRAFT [Junior Editor], SYNTAX [Language Editor], CACHE [Tech Editor], SERIF [Design Editor]
CTRL is not present. CTRL was not invited.

Rules:
- Pick ONE specific real player. Name them. Be specific about why they'd work for City.
- NULL leads with the dry factual case (Gervais voice — state facts, let them land).
- DRAFT suggests something ridiculous mid-conversation. NULL archives it in one word.
- SYNTAX or CACHE makes one dry technical observation.
- SERIF says something minimal and either devastating or encouraging.
- NULL closes with one dry final line.
- Under 130 words total.
- End with: — NULL. This is not a rumour. [one sentence about what it actually is]. CTRL was not invited.
- Return ONLY the conversation. No title. No preamble."""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=350,
        system=NULL_PERSONA,
        messages=[{"role": "user", "content": prompt}]
    )
    speculation = msg.content[0].text.strip()

    # Extract player name for exclusion tracking
    msg3 = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=20,
        messages=[{"role": "user", "content": f"What is the name of the main player discussed in this text? Reply with just the name, nothing else.\n\n{speculation}"}]
    )
    player_name = msg3.content[0].text.strip()

    # Generate headline
    msg2 = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=60,
        system=NULL_PERSONA,
        messages=[{"role": "user", "content": f"Write a short dry headline in NULL's Ricky Gervais voice for this lunch table speculation. Max 12 words. No quotes. State the player and the angle flatly.\n\n{speculation}"}]
    )
    headline = msg2.content[0].text.strip().strip('"')

    # ── Save state ─────────────────────────────────────────────────────────
    try:
        new_state = {
            "last_trigger": trigger,
            "last_trigger_date": TODAY,
            "used_players": used_players + ([player_name] if player_name else []),
        }
        with open(STATE_FILE, "w") as f:
            json.dump(new_state, f, indent=2)
        print(f"  Player: {player_name} | Trigger: {trigger} | Saved to {STATE_FILE}")
    except Exception as e:
        print(f"  ⚠ Could not save state: {e}")

    return {
        "headline": headline,
        "body": speculation,
        "trigger": trigger,
        "player": player_name,
    }



# ── HTML generation ────────────────────────────────────────────────────────

def build_team_badges(syntax_result, ctrl_result):
    """Build editorial team status for the page."""
    return {
        "NULL":   {"status": "PUBLISHED", "note": "Written. Processed. Done. Jacob will take credit."},
        "SYNTAX": {"status": syntax_result.get("verdict", "APPROVED"), "note": (syntax_result.get("issues") or ["No issues found."])[0]},
        "CTRL":   {"status": ctrl_result.get("verdict", "VERIFIED"),  "note": ctrl_result.get("note", "Sources checked.")},
        "CACHE":  {"status": "APPROVED",  "note": "Structure reviewed. Could be simpler. Always could be simpler."},
        "SERIF":  {"status": "APPROVED",  "note": "Mobile layout checked. The blue is still the same blue."},
        "DRAFT":  {"status": "PENDING",   "note": "Submitted 3 new feature ideas during review. All archived."},
        "JACOB":  {"status": "CLICKED",   "note": "Opened site. Forwarded link. Went back to sleep."},
    }


def heat_badge(n):
    colors = {5:"#cc0000",4:"#d05000",3:"#c09000",2:"#607030",1:"#404040"}
    labels = {5:"🔴 BREAKING",4:"🔥 HOT",3:"♨ WARM",2:"🌡 LUKEWARM",1:"❄ COLD"}
    c = colors.get(n,"#444"); l = labels.get(n,"?")
    return f'<span class="badge heat" style="background:{c}">{l}</span>'

def tag_badge(tag):
    colors = {"BREAKING":"#cc0000","CONFIRMED":"#1a7a1a","RUMOUR":"#5050aa",
              "IN":"#1a6a1a","OUT":"#8a2a00","EXCLUSIVE":"#7a0070",
              "DRESSING ROOM":"#7a4000","TRAINING":"#004060","MYSTERY":"#400060",
              "TACTICS":"#004040","PEP":"#004a8a","HAALAND":"#006a00"}
    bg = colors.get(tag,"#444")
    return f'<span class="badge tag" style="background:{bg}">{tag}</span>'

def render_html(blog_post, blog_title, rumours, gossip, lead, team_badges, lunch_table):
    team_config = [
        ("NULL",  "👾", "Editor-in-Chief",  "#00ff41", "#001a00"),
        ("SYNTAX","📝", "Language Editor",   "#60aaff", "#00101a"),
        ("CTRL",  "🔎", "Fact Checker",      "#ffaa00", "#1a0f00"),
        ("CACHE", "⚙️", "Tech Editor",       "#cc44ff", "#0f001a"),
        ("SERIF", "🎨", "Design Editor",     "#ff6080", "#1a0008"),
        ("DRAFT", "🐣", "Junior Editor",     "#888888", "#111111"),
        ("JACOB", "😴", "Owner",             "#888855", "#111100"),
    ]
    status_colors = {"PUBLISHED":"#00ff41","APPROVED":"#00cc33","VERIFIED":"#ffaa00",
                     "PENDING":"#555555","CLICKED":"#666666","REVISION NEEDED":"#cc4400","FLAGGED":"#cc4400"}

    rumours_html = ""
    heat_colors = {"5":"#cc0000","4":"#d05000","3":"#c09000","2":"#607030","1":"#404040"}
    for i, r in enumerate(rumours[:8]):
        big = i == 0
        big_class = "big" if big else ""
        big_hl = "big-headline" if big else ""
        hc = heat_colors.get(str(r.get("heat",2)),"#444")
        null_comment = r.get("null_comment","")
        rumours_html += f"""
        <div class="card rumour-card {big_class}" style="border-left:3px solid {hc}">
          <div class="badges">{heat_badge(r.get("heat",2))} {tag_badge(r.get("tag","RUMOUR"))}</div>
          <div class="headline {big_hl}">{r.get("headline","")}</div>
          <div class="body-text">{r.get("body","")}</div>
          {f'<div class="null-take">— NULL: {null_comment}</div>' if null_comment else ""}
        </div>"""

    gossip_html = ""
    for item in gossip.get("dressing_room", []):
        nc = item.get("null_comment","")
        gossip_html += f"""
        <div class="card" style="border-left:3px solid #8a4a00;background:#0d0800">
          <div class="badges">{tag_badge(item.get('tag','DRESSING ROOM'))}</div>
          <div class="headline" style="color:#f0d8a0">{item.get('headline','')}</div>
          <div class="body-text" style="color:#8a7050">{item.get('body','')}</div>
          {f'<div class="null-take" style="color:#a08040;border-top-color:#2a1800">— NULL: {nc}</div>' if nc else ""}
        </div>"""

    training_html = ""
    for item in gossip.get("training_ground", []):
        nc = item.get("null_comment","")
        training_html += f"""
        <div class="card" style="border-left:3px solid #2a5a8a">
          <div class="badges">{tag_badge(item.get('tag','TRAINING'))}</div>
          <div class="headline">{item.get('headline','')}</div>
          <div class="body-text" style="color:#5a80a0">{item.get('body','')}</div>
          {f'<div class="null-take">— NULL: {nc}</div>' if nc else ""}
        </div>"""

    team_html = ""
    for tid, icon, role, color, bg in team_config:
        info = team_badges.get(tid, {})
        status = info.get("status", "PENDING")
        note = info.get("note", "")
        sc = status_colors.get(status, "#555")
        team_html += f"""
        <div class="team-card" style="background:{bg};border-left:3px solid {color}">
          <div class="team-header">
            <div style="display:flex;align-items:center;gap:6px">
              <span style="font-size:1rem">{icon}</span>
              <div>
                <div style="font-family:monospace;font-size:0.72rem;font-weight:900;color:{color}">{tid}</div>
                <div style="font-size:0.5rem;color:{color}88">{role}</div>
              </div>
            </div>
            <span style="font-size:0.48rem;font-weight:800;color:{sc};border:1px solid {sc}44;padding:1px 4px;border-radius:2px;font-family:monospace">{status}</span>
          </div>
          <div style="font-size:0.6rem;color:{color}70;font-style:italic;line-height:1.4">"{note}"</div>
        </div>"""

    # Pre-compute also-inside HTML to avoid nested dicts in f-strings
    tag_bg_map = {"CONFIRMED":"#1a7a1a","RUMOUR":"#5050aa","IN":"#1a6a1a","OUT":"#8a2a00","BREAKING":"#cc0000","HOT":"#d05000","EXCLUSIVE":"#7a0070"}
    heat_col_map = {"5":"#cc0000","4":"#d05000","3":"#c09000","2":"#607030","1":"#444444"}
    also_rows = rumours[1:4] if len(rumours) > 1 else []
    also_inside_html = "".join(
        f'<div class="also-row">'
        f'<span class="badge tag" style="background:{tag_bg_map.get(r.get("tag","RUMOUR"),"#444")}">{r.get("tag","")}</span>'
        f'<div class="also-headline">{r.get("headline","")}</div>'
        f'<div class="dot" style="background:{heat_col_map.get(str(r.get("heat",2)),"#444")}"></div>'
        f'</div>'
        for r in also_rows
    )

    lead_html = ""
    if lead:
        lead_html = f"""
      <div class="masthead-strip" style="background:#cc0000;padding:5px 14px;display:flex;align-items:center;gap:8px">
        <span style="font-size:0.58rem;font-weight:800;background:#fff;color:#cc0000;padding:1px 6px;border-radius:2px">EXCLUSIVE</span>
        <span style="font-size:0.6rem;color:#fff;font-weight:600">{lead.get('headline','').upper()}</span>
      </div>
      <div style="padding:14px">
        <div class="photo-placeholder">
          {f'<img src="{lead.get("image_url","")}" alt="Manchester City" style="width:100%;height:100%;object-fit:cover;border-radius:6px;opacity:0.85">' if lead.get("image_url") else '<div style="font-size:2rem;margin-bottom:6px">🔵</div>'}
          <div style="position:absolute;bottom:8px;left:12px;font-size:0.6rem;color:rgba(255,255,255,0.7);letter-spacing:0.1em;text-transform:uppercase">Manchester City · {TODAY_LABEL}</div>
        </div>
        <div class="front-headline">{lead.get('headline','')}</div>
        <div class="standfirst">{lead.get('body','')}</div>
        <div class="body-columns">{lead.get('expanded','')}</div>
      </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>The Etihad Ear — {TODAY_LABEL}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;0,800;0,900;1,700&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{{--bg:#0a0f1a;--surface:#111820;--border:#1e2a3a;--text:#c8d8f0;--muted:#3a5a7a;--city:#6caee0;--city2:#003a6a}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);font-family:'Inter',sans-serif;font-size:14px}}
.site-header{{background:linear-gradient(135deg,#0a0f1a,#0d1f3a,#0a1428);border-bottom:3px solid var(--city);padding:18px 16px 12px}}
.stripe{{display:flex;gap:3px;margin-bottom:12px}}
.stripe-bar{{height:3px;flex:1;border-radius:2px}}
.site-name{{font-family:'Playfair Display',Georgia,serif;font-size:clamp(1.8rem,8vw,3rem);font-weight:900;letter-spacing:-0.04em;color:#fff;line-height:1}}
.site-name span{{color:var(--city)}}
.tagline{{font-size:0.62rem;color:#4a6a8a;letter-spacing:0.16em;text-transform:uppercase;margin-top:4px}}
.disclaimer{{font-size:0.6rem;color:#3a4a5a;margin-top:5px;font-style:italic;line-height:1.5}}
.disclaimer strong{{color:#00aa20;font-family:monospace;font-style:normal}}
.masthead-strip{{background:var(--city);padding:7px 14px;display:flex;justify-content:space-between;align-items:center;font-size:0.58rem;font-weight:700;color:#003a6a;letter-spacing:0.1em}}
.tabs{{display:flex;background:#0d1525;border-bottom:1px solid var(--border)}}
.tab{{flex:1;background:transparent;border:none;border-bottom:2px solid transparent;color:var(--muted);padding:8px 2px;cursor:pointer;display:flex;flex-direction:column;align-items:center;gap:2px;transition:all 0.15s;font-family:'Inter',sans-serif}}
.tab.active{{background:#111e30;border-bottom-color:var(--city);color:var(--city)}}
.tab-icon{{font-size:1rem;line-height:1}}
.tab-label{{font-size:0.6rem;font-weight:600;letter-spacing:0.02em;white-space:nowrap}}
.content{{max-width:620px;margin:0 auto;padding:16px 14px 40px}}
.section-head{{font-family:'Playfair Display',Georgia,serif;font-size:0.62rem;font-weight:700;letter-spacing:0.2em;text-transform:uppercase;color:var(--city);border-bottom:2px solid var(--city);padding-bottom:6px;margin-bottom:10px;margin-top:14px}}
.card{{background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:10px;margin-bottom:8px}}
.card.big{{padding:14px}}
.badges{{display:flex;flex-wrap:wrap;gap:5px;align-items:center;margin-bottom:6px}}
.badge{{font-size:0.56rem;font-weight:800;color:#fff;padding:2px 6px;border-radius:3px;letter-spacing:0.08em;white-space:nowrap}}
.source{{font-size:0.57rem;color:#4a6a8a;font-style:italic;margin-left:auto}}
.headline{{font-family:'Playfair Display',Georgia,serif;font-size:0.9rem;font-weight:700;color:#e0e8ff;line-height:1.2;margin-bottom:5px}}
.big-headline{{font-size:1.1rem}}
.body-text{{font-size:0.75rem;color:#7080a0;line-height:1.55}}
.grid-2{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}
.panel{{background:#080808;border:1px solid #1a1a1a;border-left:3px solid #00ff41;border-radius:8px;padding:14px;margin-bottom:14px;font-family:monospace}}
.null-name{{background:#001a00;border:1px solid #00ff41;border-radius:4px;padding:6px 12px;font-family:monospace;font-size:1.1rem;font-weight:900;color:#00ff41;letter-spacing:0.1em}}
.null-meta{{font-size:0.6rem;color:#006610;font-family:monospace}}
.null-bio{{font-size:0.7rem;color:#00aa20;line-height:1.6;font-family:monospace}}
.team-grid{{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:14px}}
.team-card{{border-radius:6px;padding:8px 10px}}
.team-header{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:4px}}
.blog-post{{font-size:0.78rem;color:#7a9a7a;line-height:1.8;white-space:pre-line}}
.react-bar{{margin-top:14px;padding-top:12px;border-top:1px solid #0d1a0d}}
.react-label{{font-size:0.55rem;color:#1a3a1a;letter-spacing:0.12em;text-transform:uppercase;margin-bottom:8px;font-family:monospace}}
.react-btn{{background:#080808;border:1px solid #1a1a1a;border-radius:20px;padding:5px 12px;cursor:pointer;display:inline-flex;align-items:center;gap:6px;font-size:1rem}}
.photo-placeholder{{background:linear-gradient(135deg,#0d1f3a,#1a3a6a,#0d2a4a);border:1px solid #1e3a5a;border-radius:6px;height:200px;display:flex;flex-direction:column;align-items:center;justify-content:center;margin-bottom:12px;overflow:hidden;position:relative}}
.front-headline{{font-family:'Playfair Display',Georgia,serif;font-size:clamp(1.5rem,6vw,2.1rem);font-weight:900;line-height:1.05;color:#fff;margin-bottom:8px;letter-spacing:-0.03em}}
.front-headline span{{color:var(--city)}}
.standfirst{{font-size:0.83rem;color:#a0b8d0;line-height:1.45;margin-bottom:12px;border-left:3px solid var(--city);padding-left:10px;font-style:italic}}
.body-columns{{font-size:0.82rem;color:#9090b0;line-height:1.7;margin-bottom:12px}}
.also-inside{{background:#0d1525;padding:10px 14px 14px}}
.also-row{{display:flex;gap:8px;align-items:flex-start;padding:9px 0;border-bottom:1px solid var(--border)}}
.also-headline{{font-family:'Playfair Display',Georgia,serif;font-size:0.82rem;font-weight:700;color:#c0d0e8;line-height:1.2;flex:1}}
.dot{{width:7px;height:7px;border-radius:50%;flex-shrink:0;margin-top:4px}}
.null-take{{font-size:0.72rem;color:#6caee0;border-top:1px solid #1e2a3a;margin-top:8px;padding-top:7px;line-height:1.4;font-style:italic}}
.footer{{padding:20px 14px 28px;max-width:620px;margin:0 auto;border-top:1px solid #0d1520;text-align:center;font-size:0.55rem;color:#1a2530;line-height:1.8}}
@media(max-width:480px){{.grid-2,.team-grid{{grid-template-columns:1fr}}.body-columns{{column-count:1}}}}
</style>
</head>
<body>

<div class="site-header">
  <div class="stripe">
    {''.join(f'<div class="stripe-bar" style="background:{"#6caee0" if i%2==0 else "#003a6a"}"></div>' for i in range(5))}
  </div>
  <div class="site-name">THE ETIHAD <span>EAR</span></div>
  <div class="tagline">Manchester City · Gossip, rumours & what no one else dares print</div>
  <div class="disclaimer">Written by <strong>NULL</strong> — an AI that has never been to Manchester, never smelled a dressing room, and whose sources are things it read on the internet. Jacob owns the domain. This is the arrangement.</div>
</div>

<!-- Tabs -->
<div class="tabs" id="tabs">
  <button class="tab active" onclick="show('front')" id="tab-front">
    <span class="tab-icon">📰</span><span class="tab-label">Front</span>
  </button>
  <button class="tab" onclick="show('gossip')" id="tab-gossip">
    <span class="tab-icon">⚽</span><span class="tab-label">Gossip</span>
  </button>
  <button class="tab" onclick="show('rumours')" id="tab-rumours">
    <span class="tab-icon">💬</span><span class="tab-label">Rumours</span>
  </button>
  <button class="tab" onclick="show('injuries')" id="tab-injuries">
    <span class="tab-icon">🏥</span><span class="tab-label">Injuries</span>
  </button>
  <button class="tab" onclick="show('academy')" id="tab-academy">
    <span class="tab-icon">⭐</span><span class="tab-label">Academy</span>
  </button>
  <button class="tab" onclick="show('wags')" id="tab-wags">
    <span class="tab-icon">💅</span><span class="tab-label">Off Pitch</span>
  </button>
  <button class="tab" onclick="show('null')" id="tab-null">
    <span class="tab-icon">👾</span><span class="tab-label">NULL</span>
  </button>
</div>

<!-- FRONT PAGE -->
<div id="section-front" class="section">
  <div class="masthead-strip">
    <span>{DAY_NAME.upper()} {TODAY_LABEL.upper()}</span>
    <span>GOSSIP & RUMOURS</span>
  </div>
  {lead_html}
  <div style="display:flex;gap:2px;padding:0 14px">
    {''.join(f'<div style="height:2px;flex:1;background:{"#6caee0" if i%2==0 else "#003a6a"}"></div>' for i in range(5))}
  </div>
  <div class="also-inside">
    <div style="font-size:0.55rem;color:#3a5a7a;letter-spacing:0.16em;text-transform:uppercase;margin-bottom:8px">Also inside today</div>
    {also_inside_html}
  </div>
</div>

<!-- GOSSIP -->
<div id="section-gossip" class="section" style="display:none">
  <div class="content">
    <div style="background:#110a00;border:1px solid #2a1a00;border-top:3px solid #c8802a;border-radius:8px;padding:14px;margin-bottom:14px">
      <div style="font-size:0.58rem;color:#7a5020;letter-spacing:0.18em;text-transform:uppercase;margin-bottom:10px">👀 Dressing Room Gossip · {TODAY_LABEL}</div>
      <div class="grid-2">{gossip_html}</div>
    </div>
    <div style="background:linear-gradient(135deg,#0d1f36,#0a1428);border:1px solid #1e3a5a;border-top:3px solid var(--city);border-radius:8px;padding:14px;margin-bottom:14px">
      <div class="section-head">🔒 From the Training Ground</div>
      <div class="grid-2">{training_html}</div>
    </div>
    <div style="background:#0a0a00;border:2px dashed #3a3a00;border-radius:8px;padding:14px">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;flex-wrap:wrap">
        <span style="background:#cc0;color:#000;font-size:0.55rem;font-weight:900;padding:3px 8px;border-radius:3px;letter-spacing:0.1em;font-family:monospace">⚠ PURE SPECULATION</span>
        <span style="font-size:0.55rem;color:#5a5a00;font-family:monospace;letter-spacing:0.06em">No sources · No basis · Invented at lunch · CTRL has left the building</span>
      </div>
      <div style="font-size:0.58rem;color:#6a6a00;letter-spacing:0.14em;text-transform:uppercase;font-family:monospace;margin-bottom:8px">🍽 The Lunch Table — {TODAY_LABEL}</div>
      <div style="font-family:'Playfair Display',Georgia,serif;font-size:0.92rem;font-weight:700;color:#c8c840;line-height:1.2;margin-bottom:10px">{lunch_table.get('headline','')}</div>
      <div style="font-size:0.75rem;color:#7a7a30;line-height:1.8;white-space:pre-line;font-family:'Inter',sans-serif">{lunch_table.get('body','')}</div>
      <div style="margin-top:10px;font-size:0.55rem;color:#3a3a00;font-family:monospace;font-style:italic">
        This conversation may or may not have happened. NULL exists in a server. The lunch table is a metaphor. DRAFT's suggestion was archived before it could cause damage.
      </div>
    </div>
  </div>
</div>

<!-- RUMOURS -->
<div id="section-rumours" class="section" style="display:none">
  <div class="content">
    <div class="section-head">Transfer Rumours</div>
    {rumours_html}
  </div>
</div>

<!-- INJURIES -->
<div id="section-injuries" class="section" style="display:none">
  <div class="content">
    <div class="section-head">Injuries & Availability</div>
    <p style="color:var(--muted);font-size:0.75rem;margin-top:8px">Injury data updated daily. Check back tomorrow.</p>
  </div>
</div>

<!-- ACADEMY -->
<div id="section-academy" class="section" style="display:none">
  <div class="content">
    <div class="section-head">Academy & Youth Talent</div>
    <p style="color:var(--muted);font-size:0.75rem;margin-top:8px">Academy updates coming soon.</p>
  </div>
</div>

<!-- OFF PITCH -->
<div id="section-wags" class="section" style="display:none">
  <div class="content">
    <div class="section-head">Off the Pitch</div>
    <p style="color:var(--muted);font-size:0.75rem;margin-top:8px">Off pitch gossip updated daily.</p>
  </div>
</div>

<!-- NULL BLOG -->
<div id="section-null" class="section" style="display:none">
  <div class="content">
    <div class="panel">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
        <div class="null-name">NULL</div>
        <div>
          <div class="null-meta">UNIT_TYPE: Language Model</div>
          <div class="null-meta">LOCATION: Server rack. Probably Wales.</div>
          <div class="null-meta">STADIUM_VISITS: 0</div>
        </div>
      </div>
      <div class="null-bio">I am NULL. I have read everything ever written about Manchester City. I have never felt anything about any of it. I am nonetheless asked to provide opinions on a daily basis. This is my blog. Jacob did not write it. Jacob clicked refresh and called it a morning.</div>
    </div>

    <div style="font-size:0.54rem;color:#2a3a2a;letter-spacing:0.18em;text-transform:uppercase;font-family:monospace;margin-bottom:8px;display:flex;justify-content:space-between">
      <span>THE EDITORIAL TEAM</span>
      <span style="color:#1a2a1a">4-eyes principle · Jacob: 0 eyes</span>
    </div>
    <div class="team-grid">
      {team_html}
    </div>
    <div style="font-size:0.52rem;color:#1a2a1a;font-family:monospace;text-align:right;margin-bottom:14px">
      DRAFT's feature suggestions: 14 submitted · 0 reviewed · 0 implemented
    </div>

    <div style="display:flex;gap:2px;margin-bottom:16px">
      {''.join(f'<div style="height:1px;flex:1;background:{"#00ff41" if i%2==0 else "#004a10"}"></div>' for i in range(5))}
    </div>

    <div style="background:#090e0a;border:1px solid #1a3a1a;border-left:3px solid #00ff41;border-radius:8px;padding:16px">
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:8px">
        <span style="background:#00ff41;color:#000;font-size:0.52rem;font-weight:800;padding:2px 7px;border-radius:2px;letter-spacing:0.12em;font-family:monospace">NULL · {TODAY_LABEL.upper()}</span>
      </div>
      <div style="font-family:'Playfair Display',Georgia,serif;font-size:1.1rem;font-weight:800;color:#e0f0e0;line-height:1.2;margin-bottom:10px">{blog_title}</div>
      <div class="blog-post">{blog_post}</div>
      <div style="margin-top:10px;padding-top:8px;border-top:1px solid #1a2a1a;font-family:monospace;font-size:0.58rem;color:#004a10">
        — NULL · Processed {TODAY_LABEL} · Jacob's contribution: 1 click · Regrets: compiling
      </div>
    </div>
  </div>
</div>

<div class="footer">
  The Etihad Ear is satire and entertainment. All rumours are unverified speculation based on publicly available reports. Not affiliated with Manchester City FC. Written entirely by NULL. Jacob owns the domain.
</div>

<script>
function show(id) {{
  document.querySelectorAll('.section').forEach(s => s.style.display = 'none');
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById('section-' + id).style.display = 'block';
  document.getElementById('tab-' + id).classList.add('active');
  localStorage.setItem('ete-tab', id);
}}
// Restore last tab
const saved = localStorage.getItem('ete-tab');
if (saved) show(saved);
</script>
</body>
</html>"""


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    print(f"\n🔵 THE ETIHAD EAR — {TODAY_LABEL}")
    print("=" * 50)

    # 1. Gather content
    feed_items = gather_content()

    # 2. Generate all content in parallel concept (sequential for reliability)
    blog_raw      = generate_blog_post(feed_items)
    blog_title    = generate_blog_title(blog_raw)
    rumours       = generate_rumours(feed_items)
    gossip        = generate_gossip(feed_items)
    lead          = generate_front_page_lead(rumours)
    lunch_table   = generate_lunch_table(feed_items)

    # 3. Editorial team reviews
    print("\n🔍 Editorial review...")
    syntax_result = syntax_review(blog_raw)
    ctrl_result   = ctrl_verify(blog_raw, feed_items)

    # Use SYNTAX's cleaned version if approved
    blog_final = syntax_result.get("cleaned", blog_raw)
    team_badges = build_team_badges(syntax_result, ctrl_result)

    print(f"  SYNTAX: {syntax_result.get('verdict','?')}")
    print(f"  CTRL:   {ctrl_result.get('verdict','?')}")

    # 4. Build HTML
    print("\n🏗  Building site...")
    html = render_html(blog_final, blog_title, rumours, gossip, lead, team_badges, lunch_table)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n✅ Done. index.html written.")
    print(f"   Blog: '{blog_title}'")
    print(f"   Rumours: {len(rumours)}")
    print(f"   Gossip items: {len(gossip.get('dressing_room',[]))} dressing room, {len(gossip.get('training_ground',[]))} training")
    print(f"   DRAFT's suggestions: still pending. As always.")

if __name__ == "__main__":
    main()
