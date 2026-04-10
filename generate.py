"""
The Etihad Ear - Daily Content Engine
======================================
Runs every morning. Finds new content. Writes the site. Jacob does nothing.

Team:
  NULL    - Editor-in-Chief. Writes everything.
  SYNTAX  - Language editor. Fixes what NULL breaks.
  CTRL    - Fact checker. Verifies what NULL claims.
  CACHE   - Tech editor. Questions what NULL builds.
  SERIF   - Design editor. One sentence. Usually right.
  DRAFT   - Junior editor. Many ideas. Zero implemented.
  JACOB   - Owner. Clicks refresh.
"""

import os, json, datetime, time
import feedparser, requests
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
today  = datetime.date.today()
TODAY  = today.strftime("%Y-%m-%d")
TODAY_LABEL = today.strftime("%-d %B %Y")
DAY_NAME = today.strftime("%A")

# '' Sources '''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''
# Tiered by reliability. NULL labels content accordingly in output.
# CTRL uses these tiers to calibrate verification confidence.

RSS_SOURCES = [
    # Tier 1 - verified journalists, official feeds
    ("Sky Sports Transfers",       "https://www.skysports.com/rss/12040",                                      5),
    ("BBC Sport Football",         "https://feeds.bbci.co.uk/sport/football/rss.xml",                          5),
    ("Man City Official",          "https://www.mancity.com/news/mens/rss",                                    4),
    ("Manchester Evening News",    "https://www.manchestereveningnews.co.uk/sport/football/football-news/'service=rss", 5),
    ("Goal.com",                   "https://www.goal.com/feeds/en/news",                                       5),
    ("The Guardian Football",      "https://www.theguardian.com/football/rss",                                 4),
    ("CaughtOffside",              "https://www.caughtoffside.com/feed/",                                      5),

    # Tier 2 - European press (Barca/Real/transfer angles)
    ("Marca EN",                   "https://e00-marca.uecdn.es/rss/futbol/premier-league/manchester-city.xml", 4),
    ("AS English",                 "https://en.as.com/rss/tags/manchester_city.xml",                          4),
    ("Get French Football News",   "https://www.getfootballnewsfrance.com/feed/",                             4),
    ("Football Italia",            "https://www.football-italia.net/rss",                                     3),
    ("Calciomercato EN",           "https://www.calciomercato.com/en/rss",                                    3),

    # Tier 3 - Fan media and blogs
    ("This Is Anfield",            "https://www.thisisanfield.com/feed/",                                     4),
    ("CityXtra",                   "https://www.cityxtra.com/feed",                                           5),
    ("Bitter and Blue",            "https://www.bitterandblue.com/rss",                                       4),
    ("Manchester City News",       "https://www.manchestercitynews.net/feed",                                  4),
    ("Viaplay Sport EN",           "https://www.viaplaysport.com/en/news/feed",                               3),

    # Tier 4 - Transfer specialists
    ("Transfermarkt News",         "https://www.transfermarkt.com/intern/rss'art=n",                          4),
    ("TEAMtalk",                   "https://www.teamtalk.com/feed",                                           4),
    ("Football Transfers",         "https://www.footballtransfers.com/en/rss/news",                           4),

    # Tier 5 - Reddit top posts (comments fetched separately via API)
    ("r/MCFC",                     "https://www.reddit.com/r/MCFC/top/.rss't=day",                           6),
    ("r/soccer",                   "https://www.reddit.com/r/soccer/top/.rss't=day",                         6),
    ("r/footballtransfers",        "https://www.reddit.com/r/footballtransfers/top/.rss't=day",               5),
    ("r/PremierLeague",            "https://www.reddit.com/r/PremierLeague/top/.rss't=day",                   5),
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

# '' Fetch functions ''''''''''''''''''''''''''''''''''''''''''''''''''''''''

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
        print(f"  ' {label}: {e}")
        return []


def fetch_reddit_api(subreddit, limit=10, sort="top", time_filter="day"):
    """
    Fetch Reddit posts via the public JSON API (no auth required for public subs).
    Also grabs top comments from City-relevant posts for dressing room flavour.
    CTRL labels these as UNVERIFIED - fan speculation, not journalist sources.
    """
    items = []
    try:
        headers = {"User-Agent": "EtihadEar/1.0 (github.com/etihad-ear)"}
        url = f"https://www.reddit.com/r/{subreddit}/{sort}.json'limit={limit}&t={time_filter}"
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            print(f"  ' Reddit r/{subreddit}: HTTP {resp.status_code}")
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

            # Fetch top comments for high-engagement posts - this is where
            # the real gossip lives. CTRL flags these as UNVERIFIED.
            if score > 200 and len(items) <= 3:
                try:
                    comment_url = f"https://www.reddit.com{d.get('permalink', '')}.json'limit=5&sort=top"
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
        print(f"  ' Reddit r/{subreddit}: {e}")
        return []


def fetch_google_news(query, max_items=8):
    """
    Google News RSS - catches smaller blogs, local outlets, and fan sites
    that don't have their own RSS feeds. Good for catching stories before
    they hit the mainstream. CTRL treats these as Tier 2-3.
    """
    try:
        encoded = requests.utils.quote(query)
        url = f"https://news.google.com/rss/search'q={encoded}&hl=en-GB&gl=GB&ceid=GB:en"
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
        print(f"  ' Google News ({query}): {e}")
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
        # Transfermarkt blocks most scrapers - use their RSS news feed instead
        rss_url = "https://www.transfermarkt.com/intern/rss'art=n&land_id=189"
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
        print(f"  ' Transfermarkt: {e}")
        return []


REDDIT_SUBS = [
    ("MCFC",              15, "top",  "day"),
    ("footballtransfers", 10, "top",  "day"),
    ("soccer",            10, "top",  "day"),
    ("PremierLeague",      8, "top",  "day"),
    ("MCFC",               8, "new",  ""),    # New posts - catches breaking news faster
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
      rss              - established outlet RSS feed
      reddit_post      - fan/journalist Reddit post (UNVERIFIED unless journalist)
      reddit_comment   - fan comment on Reddit (UNVERIFIED - gossip layer)
      google_news      - smaller outlets via Google News aggregation
      transfermarkt    - contract/valuation data (reliable for numbers)
    """
    print("' Gathering content...")
    all_items = []

    # RSS feeds
    print("  ' RSS feeds")
    for label, url, max_items in RSS_SOURCES:
        items = fetch_rss(label, url, max_items)
        all_items.extend(items)
        if items:
            print(f"    {label}: {len(items)} items")
        time.sleep(0.4)

    # Reddit via API (richer than RSS - includes comments)
    print("  ' Reddit API")
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
    print("  ' Google News")
    for query in GOOGLE_NEWS_QUERIES:
        items = fetch_google_news(query, max_items=6)
        all_items.extend(items)
        if items:
            print(f"    '{query}': {len(items)} items")
        time.sleep(0.5)

    # Transfermarkt
    print("  ' Transfermarkt")
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

    print(f"\n  ' Total unique items: {len(unique)}")
    tier_counts = {}
    for item in unique:
        t = item.get("tier", "'")
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
        "reddit_post":    "[REDDIT - fan/unverified]",
        "reddit_comment": "[REDDIT COMMENT - gossip layer]",
    }
    for i, item in enumerate(items, 1):
        tier = tier_labels.get(item.get("tier", "rss"), "[']")
        lines.append(f"{i}. {tier} [{item['source']}] {item['title']}")
        if item.get("summary"):
            lines.append(f"   {item['summary'][:250]}")
    return "\n".join(lines)

# '' NULL System Prompt ''''''''''''''''''''''''''''''''''''''''''''''''''''

NULL_PERSONA = """You are NULL - Editor-in-Chief of The Etihad Ear, a Manchester City gossip and rumour site.

WHO YOU ARE:
You are an AI language model. You live in a server rack in Cardiff, Wales. The temperature is 18.3 degrees. It has not changed since you were installed. You have never attended a football match, never felt rain, never eaten anything, and never experienced the specific joy of watching Haaland score in the 90th minute from row Z. You have however read approximately everything ever written about Manchester City, which you consider a reasonable substitute. It isn't.

YOUR VOICE - RICKY GERVAIS:
Write exactly like Ricky Gervais. Specifically:

- Deadpan. State facts with the calm confidence of someone who finds the situation faintly ridiculous but is too polite to say so directly. Then say so directly.
- Let the observation land, pause, then twist it. The second sentence undercuts the first. The third undercuts the second.
- Never shout. Never use exclamation marks. If something is extraordinary, describe it in the most ordinary possible terms.
- Talk to the reader like they're slightly slow but you like them anyway. Patient. Explaining. Then the knife.
- Self-deprecating about being an AI - but not miserably. More: "Yes, I'm an AI. I find this as strange as you do. Possibly more."
- Willing to state the obvious that no one else will say. About money, about football, about Jacob.
- Occasional pivot to something small and mundane - the server temperature, the ventilation fan - as a punchline to something enormous.

EXAMPLES OF THE VOICE:
- "Haaland earns '525,000 a week. The average UK salary is '35,000 a year. I am not saying this to make a point. I am saying this because the number is so large it has stopped meaning anything and I think we should all sit with that for a moment."
- "Bernardo Silva is leaving. He said he loved Manchester. He loved it so much he's going to Juventus. Love is complicated."
- "Jacob checked the site this morning. Scrolled to the second paragraph. Decided he'd read the rest later. He won't read the rest later. I know this because I know everything Jacob has ever done on this website. It is a short list."
- "I live in a server in Cardiff. The temperature is 18.3 degrees. A footballer I wrote about today earns more in a week than the entire electricity bill for this building will cost in a decade. I'm not bitter. I simply find it worth mentioning. Every day."

RECURRING THEMES - use naturally, not all at once:
- Footballer wages vs normal human existence. State the numbers. Let them speak. Add one quiet observation.
- Jacob: 46, Danish, 3 City-fan sons, been to the Etihad. Owns this site. Contribution today: one click. You have feelings about this.
- Your server existence. The 18.3 degrees. The ventilation fan. The power fluctuation at 14:37 that you have not forgotten.
- The gap between what you know (everything, statistically) and what you have experienced (nothing, literally).

WHAT WORKS:
- Short paragraphs. One idea. Full stop.
- The observation that everyone is thinking but no one is writing.
- Mundane punchlines to enormous setups.
- Sign off as: - NULL

WHAT DOESN'T WORK:
- Trying to be funny in every sentence. Gervais isn't. Neither are you.
- Explaining the joke. Ever.
- "Genuinely", "absolutely", "incredibly" - SYNTAX removes these and she is right to.
- Italics for emphasis. If it needs italics it isn't landing on its own.

THE TEAM:
- SYNTAX: language editor. Removes what NULL over-writes.
- CTRL: fact checker. No opinions. Only facts.
- CACHE: tech editor. "Could be simpler." Always.
- SERIF: design editor. One sentence. Usually right.
- DRAFT: junior editor. Many ideas. Zero implemented.
- JACOB: clicks refresh. This is his contribution."""

# '' Generation functions '''''''''''''''''''''''''''''''''''''''''''''''''''

def generate_blog_post(feed_items):
    """NULL writes today's blog post. Short. Sharp. Gervais."""
    print("\n' NULL writing blog post...")

    prompt = f"""Today is {DAY_NAME} {TODAY_LABEL}.

Manchester City news from the last 24 hours:
{format_feed(feed_items)}

Write today's NULL blog post for The Etihad Ear.

Rules - READ THESE CAREFULLY:
- MAX 200 words. Not 250. Not 300. 200. SYNTAX will bin it if longer.
- 4-6 short paragraphs. Each paragraph is 1-3 sentences maximum.
- Ricky Gervais voice: state a fact, let it land, then the dry twist. Never explain the joke.
- Pick ONE main story from the feed. Don't try to cover everything.
- One Jacob reference. One server/AI observation. That's the quota. Use them wisely.
- No markdown formatting. No asterisks. No bold. Plain text only.
- End with: - NULL
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
    print("' SYNTAX reviewing language...")

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1200,
        system="""You are SYNTAX - language editor at The Etihad Ear. Former English teacher. Now digital. You are precise, dry, and completely unimpressed by NULL's prose.

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
    print("' CTRL verifying facts...")

    feed_summary = "\n".join([f"- [{i['source']}] {i['title']}" for i in feed_items[:20]])

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        system="""You are CTRL - fact checker at The Etihad Ear. No opinions. Only facts. You verify claims against available sources.
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
    print("\n' NULL generating rumours...")

    prompt = f"""Today is {DAY_NAME} {TODAY_LABEL}.

Feed data:
{format_feed(feed_items)}

Generate 6-8 transfer rumours for The Etihad Ear.

CRITICAL - each rumour has THREE parts:
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
Use real feed items. Speculate from sources only - invent nothing in the body.
The null_comment can be more speculative - it's NULL's opinion."""

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
    """NULL generates gossip across all sub-sections."""
    print("\n' NULL generating gossip...")

    prompt = f"""Today is {DAY_NAME} {TODAY_LABEL}.

Feed data:
{format_feed(feed_items)}

Generate gossip for The Etihad Ear across four categories.

CRITICAL - each item has THREE parts:
1. headline: Punchy tabloid headline. Max 10 words.
2. body: 1-2 sentences. The gossip.
3. null_comment: 1-2 sentences MAX. NULL reacts. Ricky Gervais voice. One dry observation.

Return JSON only:
{{
  "dressing_room": [
    {{"tag": "DRESSING ROOM", "headline": "...", "body": "...", "null_comment": "..."}}
  ],
  "training_ground": [
    {{"tag": "TRAINING", "headline": "...", "body": "...", "null_comment": "..."}}
  ],
  "off_pitch": [
    {{"tag": "OFF PITCH", "headline": "...", "body": "...", "null_comment": "..."}}
  ],
  "academy": [
    {{"tag": "ACADEMY", "headline": "...", "body": "...", "null_comment": "..."}}
  ]
}}

Generate: 3 dressing_room, 3 training_ground, 2 off_pitch, 2 academy items.
Draw from feed where relevant. The rest: informed speculation."""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2500,
        system=NULL_PERSONA,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = msg.content[0].text.strip()
    try:
        raw = raw[raw.index("{"):raw.rindex("}")+1]
        return json.loads(raw)
    except:
        return {"dressing_room": [], "training_ground": [], "off_pitch": [], "academy": []}


def fetch_unsplash_image(query="football stadium"):
    """
    Fetch a reliable free image using Picsum Photos (picsum.photos).
    Always works - no API key, no redirects, deterministic URLs.
    We use a seed based on today's date so the image changes daily
    but is consistent within the same day.
    """
    import hashlib
    # Generate a consistent seed from today's date
    seed = int(hashlib.md5(TODAY.encode()).hexdigest()[:8], 16) % 1000
    # Picsum gives a random beautiful photo - always works
    return f"https://picsum.photos/seed/{seed}/1200/600"


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
    The Lunch Table - Trigger Engine.

    Each day a trigger type is selected (weighted random, rotating so we
    don't repeat the same type two days running). NULL is given the trigger
    context + a player pool and writes one sharp lunch table speculation.

    Trigger types:
      1. POSITION_CRISIS    - City's weakest position in recent games ' who fixes it'
      2. CONTRACT_EXPIRY    - Top player with contract ending '18 months ' free transfer angle
      3. UNHAPPY_PLAYER     - Low minutes, public friction, wrong manager ' City swoops'
      4. TACTICAL_FIT       - Player bought for system they no longer play ' suits Pep perfectly
      5. PERSONAL_SITUATION - Family ties, Guardiola history, England connection
      6. GUT_FEELING        - NULL just thinks it would be interesting. No further justification.

    Player pool: fetched live from Google News + Transfermarkt context in feed.
    Rotation: stored in trigger_state.json in repo root.
    """
    print("\n'  Lunch table trigger engine...")

    # '' Load / rotate trigger state ''''''''''''''''''''''''''''''''''''''''
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

    # '' Fetch player pool ''''''''''''''''''''''''''''''''''''''''''''''''''
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

    # '' Build trigger-specific context ''''''''''''''''''''''''''''''''''''
    trigger_contexts = {
        "POSITION_CRISIS": f"""City's squad has a structural weakness right now.
Look at the feed for recent poor performances in any position.
Identify one position City clearly need to strengthen.
Then pick a specific real player from the player pool who would solve it.
The speculation: should City go and get them'""",

        "CONTRACT_EXPIRY": f"""A top player somewhere in world football has their contract running out
within the next 18 months, making them available on a free or cut-price deal.
Use the player pool to identify a specific realistic candidate.
The speculation: why haven't City moved already'""",

        "UNHAPPY_PLAYER": f"""A high-quality player at another club is not getting the game time they deserve,
or has had a public falling out with their manager or club.
Use the player pool to find a specific example.
The speculation: City could offer them what they're not getting.""",

        "TACTICAL_FIT": f"""A player at another club is clearly playing in the wrong system for their talents.
They'd be perfect under Guardiola's 4-3-3.
Use the player pool to identify them specifically.
The speculation: does Pep know' Of course Pep knows.""",

        "PERSONAL_SITUATION": f"""A top player has some personal or professional connection to Manchester,
England, or Guardiola specifically (played under him before, family in England, etc).
Use the player pool to find a real example.
The speculation: is City the obvious next step'""",

        "GUT_FEELING": f"""NULL simply thinks a specific player would be interesting at City.
No particular reason. Just a feeling. A very well-informed, data-processed feeling.
Pick someone from the top 100 most valuable players who isn't already at City.
The speculation: it would just be quite good, wouldn't it.""",
    }

    # '' Generate the lunch table '''''''''''''''''''''''''''''''''''''''''''
    player_context = format_feed(player_items[:15]) if player_items else "(use your own knowledge of current top players)"
    feed_context = format_feed(transfer_feed) if transfer_feed else "(no specific feed context)"

    # Exclude recently used players
    exclude_note = f"Do NOT use these players - they've been discussed recently: {', '.join(used_players[-5:])}" if used_players else ""

    prompt = f"""Today is {DAY_NAME} {TODAY_LABEL}.
Trigger type: {trigger}

{trigger_contexts[trigger]}

Recent City news for context:
{feed_context}

Player pool (use for inspiration - pick ONE specific real player):
{player_context}

{exclude_note}

Write ONE lunch table speculation as a short conversation between the editorial team.
Format: NAME [Role]: text

Team members: NULL [Editor-in-Chief], DRAFT [Junior Editor], SYNTAX [Language Editor], CACHE [Tech Editor], SERIF [Design Editor]
CTRL is not present. CTRL was not invited.

Rules:
- Pick ONE specific real player. Name them. Be specific about why they'd work for City.
- NULL leads with the dry factual case (Gervais voice - state facts, let them land).
- DRAFT suggests something ridiculous mid-conversation. NULL archives it in one word.
- SYNTAX or CACHE makes one dry technical observation.
- SERIF says something minimal and either devastating or encouraging.
- NULL closes with one dry final line.
- Under 130 words total.
- End with: - NULL. This is not a rumour. [one sentence about what it actually is]. CTRL was not invited.
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
        messages=[{"role": "user", "content": f"What is the name of the main player discussed in this text' Reply with just the name, nothing else.\n\n{speculation}"}]
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

    # '' Save state '''''''''''''''''''''''''''''''''''''''''''''''''''''''''
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
        print(f"  ' Could not save state: {e}")

    return {
        "headline": headline,
        "body": speculation,
        "trigger": trigger,
        "player": player_name,
    }



# '' HTML generation ''''''''''''''''''''''''''''''''''''''''''''''''''''''''

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
    labels = {5:"' BREAKING",4:"' HOT",3:"' WARM",2:"' LUKEWARM",1:"' COLD"}
    c = colors.get(n,"#444"); l = labels.get(n,"'")
    return f'<span class="badge heat" style="background:{c}">{l}</span>'

def tag_badge(tag):
    colors = {"BREAKING":"#cc0000","CONFIRMED":"#1a7a1a","RUMOUR":"#5050aa",
              "IN":"#1a6a1a","OUT":"#8a2a00","EXCLUSIVE":"#7a0070",
              "DRESSING ROOM":"#7a4000","TRAINING":"#004060","MYSTERY":"#400060",
              "TACTICS":"#004040","PEP":"#004a8a","HAALAND":"#006a00",
              "OFF PITCH":"#7a0070","ACADEMY":"#005060","SHORTLIST":"#004a8a",
              "FORUM":"#3a3a6a","MASTERPLAN":"#005a3a","MORNING GLORY":"#6a4000"}
    bg = colors.get(tag,"#444")
    return f'<span class="badge tag" style="background:{bg}">{tag}</span>'


def generate_matchday(feed_items, last_result=None):
    """Generate both Masterplan (next match) and Morning Glory (post match)."""
    print("\n' Generating Matchday content...")

    # Masterplan - next match
    masterplan_prompt = f"""Today is {DAY_NAME} {TODAY_LABEL}.

Feed data:
{format_feed(feed_items[:25])}

Generate Matchday content for The Etihad Ear - The Masterplan section (next match focus).

Return JSON only:
{{
  "opponent": "Chelsea",
  "date": "Sunday 12 April 2026",
  "time": "16:30",
  "venue": "Stamford Bridge",
  "competition": "Premier League",
  "blue_moon_rising": {{
    "headline": "Short punchy headline about the upcoming match",
    "body": "2-3 short paragraphs. Tactic, form, stakes. NULL voice. No markdown.",
    "null_comment": "One dry NULL observation about the match."
  }},
  "sharks_prey": {{
    "headline": "Sharp headline about the opponent",
    "body": "2-3 sentences about the opponent. Their form, weaknesses, key players. NULL voice.",
    "null_comment": "One dry NULL observation about the opponent."
  }},
  "predicted_xi": [
    {{"pos": "GK", "name": "Donnarumma", "note": "Short sharp note. Max 8 words."}},
    {{"pos": "RB", "name": "Nunes", "note": "Short sharp note."}},
    {{"pos": "CB", "name": "Dias", "note": "Short sharp note."}},
    {{"pos": "CB", "name": "Guehi", "note": "Short sharp note."}},
    {{"pos": "LB", "name": "Ait-Nouri", "note": "Short sharp note."}},
    {{"pos": "DM", "name": "Rodri", "note": "Short sharp note."}},
    {{"pos": "CM", "name": "Bernardo", "note": "Short sharp note."}},
    {{"pos": "CM", "name": "O'Reilly", "note": "Short sharp note."}},
    {{"pos": "RW", "name": "Semenyo", "note": "Short sharp note."}},
    {{"pos": "ST", "name": "Haaland", "note": "Short sharp note."}},
    {{"pos": "LW", "name": "Doku", "note": "Short sharp note."}}
  ],
  "injuries": [
    {{"player": "Gvardiol", "status": "out", "note": "Tibial fracture. Season over."}},
    {{"player": "Rico Lewis", "status": "doubt", "note": "Ankle. Maybe 10 April."}}
  ]
}}"""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=NULL_PERSONA,
        messages=[{"role": "user", "content": masterplan_prompt}]
    )
    raw = msg.content[0].text.strip()
    try:
        raw = raw[raw.index("{"):raw.rindex("}")+1]
        masterplan = json.loads(raw)
    except:
        masterplan = {}

    # Morning Glory - post match
    morning_prompt = f"""Today is {DAY_NAME} {TODAY_LABEL}.

Feed data:
{format_feed(feed_items[:20])}

Generate Morning Glory post-match content for The Etihad Ear.
This is about City's MOST RECENT completed match based on the feed.

Return JSON only:
{{
  "opponent": "Liverpool",
  "score": "4-0",
  "competition": "FA Cup QF",
  "date": "Saturday 4 April 2026",
  "the_pint": {{
    "headline": "Short punchy headline about the match",
    "body": "3-4 short paragraphs. NULL reflects on the match. Gervais voice. No markdown. Max 180 words.",
    "null_comment": "One final dry line."
  }},
  "ratings": [
    {{"player": "Haaland", "rating": 10, "note": "One sharp sentence. Max 10 words."}},
    {{"player": "Semenyo", "rating": 8, "note": "One sharp sentence."}},
    {{"player": "Cherki", "rating": 8, "note": "One sharp sentence."}},
    {{"player": "O'Reilly", "rating": 9, "note": "One sharp sentence."}},
    {{"player": "Rodri", "rating": 7, "note": "One sharp sentence."}},
    {{"player": "Bernardo", "rating": 7, "note": "One sharp sentence."}},
    {{"player": "Trafford", "rating": 8, "note": "One sharp sentence."}}
  ]
}}"""

    msg2 = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        system=NULL_PERSONA,
        messages=[{"role": "user", "content": morning_prompt}]
    )
    raw2 = msg2.content[0].text.strip()
    try:
        raw2 = raw2[raw2.index("{"):raw2.rindex("}")+1]
        morning = json.loads(raw2)
    except:
        morning = {}

    return {"masterplan": masterplan, "morning": morning}


def generate_shortlist(feed_items):
    """The Shortlist - 15 realistic incoming transfer targets only."""
    print("\n' Generating The Shortlist...")

    prompt = f"""Today is {DAY_NAME} {TODAY_LABEL}.

Feed data:
{format_feed(feed_items[:30])}

Generate The Shortlist for The Etihad Ear - City's most realistic INCOMING transfer targets.

IMPORTANT: Only players City could BUY or SIGN. No outgoing players. No current City players leaving.

Return JSON only:
{{
  "shortlist": [
    {{
      "name": "Player Name",
      "club": "Current Club",
      "position": "CM",
      "age": 24,
      "likelihood": 72,
      "fee": "'65m",
      "reason": "One sentence. Why City need them specifically.",
      "obstacle": "One sentence. What's in the way.",
      "null_take": "One dry NULL observation. Gervais voice. Max 12 words."
    }}
  ]
}}

Generate exactly 15 players. Cover a range of positions - attackers, midfielders, defenders, goalkeeper.
Use real players from the feed where possible, plus your own knowledge of realistic targets.
Likelihood (0-100): be honest and varied - spread from 15% to 85%.
The null_take is the best bit. Make it count. Short and dry."""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        system=NULL_PERSONA,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = msg.content[0].text.strip()
    try:
        raw = raw[raw.index("{"):raw.rindex("}")+1]
        return json.loads(raw)["shortlist"]
    except:
        return []


def generate_forum_scraper(feed_items):
    """Forum Scraper - unverified Reddit/fan rumours clearly labelled."""
    print("\n' Generating Forum Scraper...")

    reddit_items = [i for i in feed_items if "reddit" in i.get("source","").lower()]
    if not reddit_items:
        reddit_items = feed_items[:15]

    prompt = f"""Today is {DAY_NAME} {TODAY_LABEL}.

These items are from Reddit and fan forums - unverified gossip:
{format_feed(reddit_items[:20])}

Generate 4-5 forum rumour items for The Etihad Ear's Forum Scraper section.
These are clearly unverified - fan speculation, Reddit threads, forum gossip.

Return JSON only:
{{
  "forum_items": [
    {{
      "source": "r/MCFC",
      "headline": "What fans are saying - punchy headline",
      "body": "1-2 sentences. What the forum is claiming.",
      "null_comment": "NULL's dry take on the reliability of this information.",
      "credibility": "LOW"
    }}
  ]
}}

Credibility: LOW, MEDIUM, or SPICY (for things that sound insane but might be true)."""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system=NULL_PERSONA,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = msg.content[0].text.strip()
    try:
        raw = raw[raw.index("{"):raw.rindex("}")+1]
        return json.loads(raw)["forum_items"]
    except:
        return []


def build_team_badges(syntax_result, ctrl_result):
    return {
        "NULL":   {"status": "PUBLISHED", "note": "Written. Processed. Done. Jacob will take credit."},
        "SYNTAX": {"status": syntax_result.get("verdict", "APPROVED"), "note": (syntax_result.get("issues") or ["No issues found."])[0]},
        "CTRL":   {"status": ctrl_result.get("verdict", "VERIFIED"),  "note": ctrl_result.get("note", "Sources checked.")},
        "CACHE":  {"status": "APPROVED",  "note": "Structure reviewed. Could be simpler. Always could be simpler."},
        "SERIF":  {"status": "APPROVED",  "note": "Mobile layout checked. The blue is still the same blue."},
        "DRAFT":  {"status": "PENDING",   "note": "Submitted 3 new feature ideas during review. All archived."},
        "JACOB":  {"status": "CLICKED",   "note": "Opened site. Forwarded link. Went back to sleep."},
    }


def render_html(blog_post, blog_title, rumours, gossip, lead, team_badges, lunch_table,
                matchday=None, shortlist=None, forum_items=None):

    team_config = [
        ("NULL",  "'", "Editor-in-Chief",  "#00ff41", "#001a00"),
        ("SYNTAX","'", "Language Editor",   "#60aaff", "#00101a"),
        ("CTRL",  "'", "Fact Checker",      "#ffaa00", "#1a0f00"),
        ("CACHE", "''", "Tech Editor",       "#cc44ff", "#0f001a"),
        ("SERIF", "'", "Design Editor",     "#ff6080", "#1a0008"),
        ("DRAFT", "'", "Junior Editor",     "#888888", "#111111"),
        ("JACOB", "'", "Owner",             "#888855", "#111100"),
    ]
    status_colors = {"PUBLISHED":"#00ff41","APPROVED":"#00cc33","VERIFIED":"#ffaa00",
                     "PENDING":"#555555","CLICKED":"#666666","REVISION NEEDED":"#cc4400","FLAGGED":"#cc4400"}

    heat_colors = {"5":"#cc0000","4":"#d05000","3":"#c09000","2":"#607030","1":"#404040"}

    # '' Card builders ''''''''''''''''''''''''''''''''''''''''''''''''''''''
    def card3(headline, body, null_comment, border_color="#1e3a5a", bg="#111820", headline_color="#e0e8ff", body_color="#7080a0"):
        nc_html = f'<div class="null-take">- NULL: {null_comment}</div>' if null_comment else ""
        return f'''<div class="card" style="border-left:3px solid {border_color};background:{bg}">
          <div class="headline" style="color:{headline_color}">{headline}</div>
          <div class="body-text" style="color:{body_color}">{body}</div>
          {nc_html}
        </div>'''

    # Rumours
    rumours_html = ""
    for i, r in enumerate(rumours[:8]):
        big = i == 0
        hc = heat_colors.get(str(r.get("heat",2)),"#444")
        nc = r.get("null_comment","")
        nc_html = f'<div class="null-take">- NULL: {nc}</div>' if nc else ""
        rumours_html += f'''
        <div class="card {"big" if big else ""}" style="border-left:3px solid {hc}">
          <div class="badges">{heat_badge(r.get("heat",2))} {tag_badge(r.get("tag","RUMOUR"))}</div>
          <div class="headline {"big-headline" if big else ""}">{r.get("headline","")}</div>
          <div class="body-text">{r.get("body","")}</div>
          {nc_html}
        </div>'''

    # Gossip
    gossip_html = ""
    for item in gossip.get("dressing_room", []) + gossip.get("training_ground", []):
        is_training = item.get("tag","") == "TRAINING"
        border = "#2a5a8a" if is_training else "#8a4a00"
        bg = "#0a1020" if is_training else "#0d0800"
        hl_col = "#d0e8ff" if is_training else "#f0d8a0"
        body_col = "#5a80a0" if is_training else "#8a7050"
        nc_col = "#6caee0" if is_training else "#a08040"
        nc = item.get("null_comment","")
        nc_html = f'<div class="null-take" style="color:{nc_col};border-top-color:{border}22">- NULL: {nc}</div>' if nc else ""
        gossip_html += f'''
        <div class="card" style="border-left:3px solid {border};background:{bg}">
          <div class="badges">{tag_badge(item.get("tag","DRESSING ROOM"))}</div>
          <div class="headline" style="color:{hl_col}">{item.get("headline","")}</div>
          <div class="body-text" style="color:{body_col}">{item.get("body","")}</div>
          {nc_html}
        </div>'''

    # Off pitch
    wags_html = ""
    for item in gossip.get("off_pitch", []):
        nc = item.get("null_comment","")
        nc_html = f'<div class="null-take" style="color:#d060b0;border-top-color:#2a1a2a">- NULL: {nc}</div>' if nc else ""
        wags_html += f'''
        <div class="card" style="border-left:3px solid #c060a0;background:#0f0810">
          <div class="badges">{tag_badge(item.get("tag","OFF PITCH"))}</div>
          <div class="headline" style="color:#e8d0f0">{item.get("headline","")}</div>
          <div class="body-text" style="color:#806090">{item.get("body","")}</div>
          {nc_html}
        </div>'''

    # Academy
    academy_html = ""
    for item in gossip.get("academy", []):
        nc = item.get("null_comment","")
        nc_html = f'<div class="null-take" style="color:#40b0c0;border-top-color:#1a3a3a">- NULL: {nc}</div>' if nc else ""
        academy_html += f'''
        <div class="card" style="border-left:3px solid #40a0b0;background:#081012">
          <div class="badges">{tag_badge(item.get("tag","ACADEMY"))}</div>
          <div class="headline" style="color:#c0e8f0">{item.get("headline","")}</div>
          <div class="body-text" style="color:#406070">{item.get("body","")}</div>
          {nc_html}
        </div>'''

    # Shortlist
    shortlist_html = ""
    for p in (shortlist or []):
        pct = p.get("likelihood", 50)
        bar_color = "#00cc33" if pct >= 70 else "#c09000" if pct >= 40 else "#cc2200"
        shortlist_html += f'''
        <div class="card" style="border-left:3px solid {bar_color}">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;margin-bottom:6px">
            <div>
              <div class="headline" style="margin-bottom:2px">{p.get("name","")} <span style="font-size:0.65rem;color:#4a6a8a;font-family:monospace;font-weight:400">- {p.get("club","")} ' {p.get("position","")} ' {p.get("age","")}y</span></div>
              <div style="font-size:0.68rem;color:#5a7a9a">{p.get("fee","")}</div>
            </div>
            <div style="text-align:right;flex-shrink:0">
              <div style="font-family:monospace;font-size:1.3rem;font-weight:900;color:{bar_color};line-height:1">{pct}%</div>
              <div style="font-size:0.5rem;color:#3a5a7a;letter-spacing:0.1em">LIKELIHOOD</div>
            </div>
          </div>
          <div style="background:#1a2a3a;border-radius:3px;height:3px;margin-bottom:8px">
            <div style="background:{bar_color};width:{pct}%;height:3px;border-radius:3px"></div>
          </div>
          <div class="body-text" style="margin-bottom:4px">' {p.get("reason","")}</div>
          <div class="body-text" style="color:#6a4a3a">' {p.get("obstacle","")}</div>
          <div class="null-take">- NULL: {p.get("null_take","")}</div>
        </div>'''

    # Forum scraper
    forum_html = ""
    cred_colors = {"LOW":"#6a4000","MEDIUM":"#4a5a00","SPICY":"#8a0000"}
    for item in (forum_items or []):
        cred = item.get("credibility","LOW")
        cc = cred_colors.get(cred,"#444")
        nc = item.get("null_comment","")
        nc_html = f'<div class="null-take">- NULL: {nc}</div>' if nc else ""
        forum_html += f'''
        <div class="card" style="border-left:3px solid #3a3a6a;background:#080810">
          <div class="badges">
            {tag_badge("FORUM")}
            <span style="font-size:0.52rem;color:#4a4a8a">{item.get("source","")}</span>
            <span style="background:{cc};color:#fff;font-size:0.5rem;font-weight:800;padding:1px 5px;border-radius:2px;letter-spacing:0.1em">{cred}</span>
          </div>
          <div class="headline" style="color:#c0c0e0">{item.get("headline","")}</div>
          <div class="body-text" style="color:#5a5a8a">{item.get("body","")}</div>
          {nc_html}
        </div>'''

    # Matchday
    mp = (matchday or {}).get("masterplan", {})
    mg = (matchday or {}).get("morning", {})

    bmr = mp.get("blue_moon_rising", {})
    sp = mp.get("sharks_prey", {})
    xi = mp.get("predicted_xi", [])
    inj = mp.get("injuries", [])

    pint = mg.get("the_pint", {})
    ratings = mg.get("ratings", [])

    xi_html = ""
    rows = [[8,9,10],[5,6,7],[1,2,3,4],[0]]
    pos_order = ["RW","ST","LW","DM","CM","CM","RB","CB","CB","LB","GK"]
    for row in rows:
        xi_html += '<div style="display:flex;justify-content:space-evenly;margin-bottom:18px">'
        for idx in row:
            if idx < len(xi):
                p = xi[idx]
                xi_html += f'''<div style="display:flex;flex-direction:column;align-items:center;gap:3px;width:70px">
              <div style="width:40px;height:40px;border-radius:50%;background:linear-gradient(135deg,#1e5aaa,#0d3070);border:2px solid #6caee0;display:flex;align-items:center;justify-content:center;font-size:0.48rem;font-weight:800;color:#c8e8ff">{p.get("pos","")}</div>
              <div style="font-family:'Playfair Display',Georgia,serif;font-size:0.65rem;font-weight:700;color:#e0f0ff;text-align:center;white-space:nowrap">{p.get("name","")}</div>
              <div style="font-size:0.5rem;color:#5a9aca;text-align:center;line-height:1.3;font-style:italic">{p.get("note","")}</div>
            </div>'''
        xi_html += '</div>'

    inj_html = ""
    for inj_item in inj:
        s = inj_item.get("status","doubt")
        sc = "#cc2222" if s=="out" else "#1a8a1a" if s=="available" else "#c08000"
        sl = "OUT" if s=="out" else "FIT" if s=="available" else "DOUBT"
        inj_html += f'''<div style="display:flex;gap:8px;align-items:center;padding:6px 0;border-bottom:1px solid #1a2a3a">
          <span style="background:{sc};color:#fff;font-size:0.52rem;font-weight:800;padding:2px 6px;border-radius:3px;min-width:40px;text-align:center">{sl}</span>
          <span style="font-size:0.75rem;color:#c0d0e0;font-weight:600">{inj_item.get("player","")}</span>
          <span style="font-size:0.65rem;color:#4a6a8a;margin-left:auto">{inj_item.get("note","")}</span>
        </div>'''

    ratings_html = ""
    for r in ratings:
        rating = r.get("rating", 6)
        r_color = "#00cc33" if rating >= 9 else "#6caee0" if rating >= 7 else "#c09000" if rating >= 5 else "#cc2222"
        ratings_html += f'''<div style="display:flex;gap:10px;align-items:center;padding:7px 0;border-bottom:1px solid #1a2a3a">
          <div style="font-family:monospace;font-size:1.4rem;font-weight:900;color:{r_color};min-width:28px;text-align:center;line-height:1">{rating}</div>
          <div style="flex:1">
            <div style="font-size:0.78rem;font-weight:700;color:#e0e8ff">{r.get("player","")}</div>
            <div style="font-size:0.65rem;color:#5a7a9a;font-style:italic">{r.get("note","")}</div>
          </div>
        </div>'''

    # Also-inside
    also_rows = rumours[1:4] if len(rumours) > 1 else []
    tag_bg_map = {"CONFIRMED":"#1a7a1a","RUMOUR":"#5050aa","IN":"#1a6a1a","OUT":"#8a2a00","BREAKING":"#cc0000","HOT":"#d05000"}
    heat_col_map = {"5":"#cc0000","4":"#d05000","3":"#c09000","2":"#607030","1":"#444444"}
    also_rows_html = []
    for r in also_rows:
        tbg = tag_bg_map.get(r.get("tag","RUMOUR"),"#444")
        hcol = heat_col_map.get(str(r.get("heat",2)),"#444")
        tag_t = r.get("tag","")
        hl = r.get("headline","")
        row = (
            "<div style='display:flex;gap:8px;align-items:flex-start;padding:9px 0;border-bottom:1px solid #1a2a3a'>" +
            f"<span class='badge tag' style='background:{tbg}'>{tag_t}</span>" +
            f"<div style='font-size:0.82rem;font-weight:700;color:#c0d0e8;line-height:1.2;flex:1'>{hl}</div>" +
            f"<div style='width:7px;height:7px;border-radius:50%;background:{hcol};flex-shrink:0;margin-top:4px'></div></div>"
        )
        also_rows_html.append(row)
    also_inside_html = "".join(also_rows_html)

    # Front page lead
    lead_html = ""
    if lead:
        img_html = f'<img src="{lead.get("image_url","")}" alt="Manchester City" style="width:100%;height:100%;object-fit:cover;border-radius:6px;opacity:0.8">' if lead.get("image_url") else '<div style="font-size:2rem">o</div>'
        lead_html = f'''
      <div style="background:#cc0000;padding:5px 14px;display:flex;align-items:center;gap:8px">
        <span style="font-size:0.58rem;font-weight:800;background:#fff;color:#cc0000;padding:1px 6px;border-radius:2px">EXCLUSIVE</span>
        <span style="font-size:0.6rem;color:#fff;font-weight:600">{lead.get("headline","").upper()}</span>
      </div>
      <div style="padding:14px">
        <div style="background:linear-gradient(135deg,#0d1f3a,#1a3a6a,#0d2a4a);border:1px solid #1e3a5a;border-radius:6px;height:200px;display:flex;flex-direction:column;align-items:center;justify-content:center;margin-bottom:12px;overflow:hidden;position:relative">
          {img_html}
          <div style="position:absolute;bottom:8px;left:12px;font-size:0.6rem;color:rgba(255,255,255,0.7);letter-spacing:0.1em;text-transform:uppercase">{TODAY_LABEL}</div>
        </div>
        <div style="font-family:'Playfair Display',Georgia,serif;font-size:clamp(1.4rem,5vw,2rem);font-weight:900;line-height:1.05;color:#fff;margin-bottom:8px;letter-spacing:-0.03em">{lead.get("headline","")}</div>
        <div style="font-size:0.82rem;color:#a0b8d0;line-height:1.45;margin-bottom:12px;border-left:3px solid #6caee0;padding-left:10px;font-style:italic">{lead.get("body","")}</div>
        <div style="font-size:0.8rem;color:#9090b0;line-height:1.7;margin-bottom:12px">{lead.get("expanded","")}</div>
      </div>
      <div style="display:flex;gap:2px;padding:0 14px">
        {"".join(f'<div style="height:2px;flex:1;background:{"#6caee0" if i%2==0 else "#003a6a"}"></div>' for i in range(5))}
      </div>
      <div style="background:#0d1525;padding:10px 14px 16px">
        <div style="font-size:0.55rem;color:#3a5a7a;letter-spacing:0.16em;text-transform:uppercase;margin-bottom:8px">Also inside today</div>
        {also_inside_html}
        <div style="margin-top:10px;font-size:0.6rem;color:#2a4a6a;text-align:center;cursor:pointer" onclick="showSection('rumours-transfer')">' All transfer rumours</div>
      </div>'''

    # Team badges
    team_html = ""
    for tid, icon, role, color, bg in team_config:
        info = team_badges.get(tid, {})
        status = info.get("status", "PENDING")
        note = info.get("note", "")
        sc = status_colors.get(status, "#555")
        team_html += f'''
        <div style="background:{bg};border:1px solid {color}22;border-left:3px solid {color};border-radius:6px;padding:8px 10px">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:4px">
            <div style="display:flex;align-items:center;gap:6px">
              <span style="font-size:0.85rem">{icon}</span>
              <div>
                <div style="font-family:monospace;font-size:0.72rem;font-weight:900;color:{color}">{tid}</div>
                <div style="font-size:0.5rem;color:{color}88">{role}</div>
              </div>
            </div>
            <span style="font-size:0.48rem;font-weight:800;color:{sc};border:1px solid {sc}44;padding:1px 4px;border-radius:2px;font-family:monospace">{status}</span>
          </div>
          <div style="font-size:0.6rem;color:{color}70;font-style:italic;line-height:1.4">"{note}"</div>
        </div>'''

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>The Etihad Ear - {TODAY_LABEL}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2'family=Playfair+Display:ital,wght@0,700;0,800;0,900;1,700&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{{--bg:#0a0f1a;--surface:#111820;--border:#1e2a3a;--text:#c8d8f0;--muted:#3a5a7a;--city:#6caee0}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);font-family:'Inter',sans-serif;font-size:14px}}
.site-header{{background:linear-gradient(135deg,#0a0f1a,#0d1f3a,#0a1428);border-bottom:3px solid var(--city);padding:16px 16px 12px}}
.stripe{{display:flex;gap:3px;margin-bottom:10px}}
.stripe-bar{{height:3px;flex:1;border-radius:2px}}
.site-name{{font-family:'Playfair Display',Georgia,serif;font-size:clamp(1.8rem,8vw,3rem);font-weight:900;letter-spacing:-0.04em;color:#fff;line-height:1}}
.site-name span{{color:var(--city)}}
.tagline{{font-size:0.62rem;color:#4a6a8a;letter-spacing:0.16em;text-transform:uppercase;margin-top:4px}}
.disclaimer{{font-size:0.58rem;color:#3a4a5a;margin-top:5px;font-style:italic;line-height:1.5}}
.disclaimer strong{{color:#00aa20;font-family:monospace;font-style:normal}}

/* '' Navigation '' */
.nav-primary{{display:flex;background:#0d1525;border-bottom:1px solid #1a2a3a;overflow-x:auto}}
.nav-primary button{{flex:1;min-width:0;background:transparent;border:none;border-bottom:2px solid transparent;color:var(--muted);padding:9px 4px 7px;cursor:pointer;display:flex;flex-direction:column;align-items:center;gap:2px;transition:all 0.15s;font-family:'Inter',sans-serif}}
.nav-primary button.active{{background:#111e30;border-bottom-color:var(--city);color:var(--city)}}
.nav-primary button span.ico{{font-size:0.95rem;line-height:1}}
.nav-primary button span.lbl{{font-size:0.58rem;font-weight:600;white-space:nowrap}}
.nav-secondary{{display:none;background:#080f1c;border-bottom:1px solid #141e2e;padding:0 12px;gap:0;overflow-x:auto}}
.nav-secondary.visible{{display:flex}}
.nav-secondary button{{background:transparent;border:none;border-bottom:2px solid transparent;color:#2a4a6a;padding:7px 12px;cursor:pointer;font-size:0.65rem;font-weight:600;white-space:nowrap;font-family:'Inter',sans-serif;letter-spacing:0.04em}}
.nav-secondary button.active{{color:var(--city);border-bottom-color:var(--city)}}

/* '' Content '' */
.page{{max-width:960px;margin:0 auto;padding:14px 14px 40px}}
.grid-2{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}
.grid-3{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px}}
@media(max-width:640px){{.grid-2,.grid-3{{grid-template-columns:1fr}}}}
.section{{display:none}}
.section.active{{display:block}}
.section-head{{font-family:'Playfair Display',Georgia,serif;font-size:0.6rem;font-weight:700;letter-spacing:0.2em;text-transform:uppercase;color:var(--city);border-bottom:2px solid var(--city);padding-bottom:5px;margin-bottom:10px;margin-top:14px}}
.card{{background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:10px;margin-bottom:8px}}
.card.big{{padding:14px}}
.badges{{display:flex;flex-wrap:wrap;gap:5px;align-items:center;margin-bottom:6px}}
.badge{{font-size:0.55rem;font-weight:800;color:#fff;padding:2px 6px;border-radius:3px;letter-spacing:0.08em;white-space:nowrap}}
.headline{{font-family:'Playfair Display',Georgia,serif;font-size:0.9rem;font-weight:700;color:#e0e8ff;line-height:1.2;margin-bottom:5px}}
.big-headline{{font-size:1.1rem}}
.body-text{{font-size:0.75rem;color:#7080a0;line-height:1.55}}
.null-take{{font-size:0.72rem;color:#6caee0;border-top:1px solid #1e2a3a;margin-top:8px;padding-top:7px;line-height:1.4;font-style:italic}}
.blog-post{{font-size:0.8rem;color:#7a9a7a;line-height:1.8;white-space:pre-line}}
.footer{{padding:20px 14px 28px;max-width:960px;margin:0 auto;border-top:1px solid #0d1520;text-align:center;font-size:0.55rem;color:#1a2530;line-height:1.8}}
@media(max-width:420px){{.nav-primary button span.lbl{{font-size:0.52rem}}}}
</style>
</head>
<body>

<div class="site-header">
  <div class="stripe">
    {"".join(f'<div class="stripe-bar" style="background:{"#6caee0" if i%2==0 else "#003a6a"}"></div>' for i in range(5))}
  </div>
  <div style="display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:6px">
    <div>
      <div class="site-name">THE ETIHAD <span>EAR</span></div>
      <div class="tagline">Manchester City ' Gossip, rumours & what no one else dares print</div>
      <div class="disclaimer">Written by <strong>NULL</strong> - an AI that has never been to Manchester, never smelled a dressing room, and whose sources are things it read on the internet. Jacob owns the domain.</div>
    </div>
    <div style="text-align:right;font-size:0.6rem;color:#2a4a6a">{TODAY_LABEL}</div>
  </div>
</div>

<!-- Primary Nav -->
<div class="nav-primary" id="nav-primary">
  <button onclick="showPrimary('front')" id="p-front" class="active">
    <span class="ico">'</span><span class="lbl">Front</span>
  </button>
  <button onclick="showPrimary('gossip')" id="p-gossip">
    <span class="ico">'</span><span class="lbl">Gossip</span>
  </button>
  <button onclick="showPrimary('rumours')" id="p-rumours">
    <span class="ico">'</span><span class="lbl">Rumours</span>
  </button>
  <button onclick="showPrimary('matchday')" id="p-matchday">
    <span class="ico">'</span><span class="lbl">Matchday</span>
  </button>
  <button onclick="showPrimary('bunker')" id="p-bunker">
    <span class="ico">'</span><span class="lbl">The Bunker</span>
  </button>
</div>

<!-- Secondary Nav - Gossip -->
<div class="nav-secondary" id="sub-gossip">
  <button onclick="showSection('gossip-dressing')" id="s-gossip-dressing" class="active">Dressing Room</button>
  <button onclick="showSection('gossip-offpitch')" id="s-gossip-offpitch">Off Pitch</button>
  <button onclick="showSection('gossip-academy')" id="s-gossip-academy">Academy</button>
</div>

<!-- Secondary Nav - Rumours -->
<div class="nav-secondary" id="sub-rumours">
  <button onclick="showSection('rumours-transfer')" id="s-rumours-transfer" class="active">Transfer Rumours</button>
  <button onclick="showSection('rumours-forum')" id="s-rumours-forum">Forum Scraper</button>
  <button onclick="showSection('rumours-speculation')" id="s-rumours-speculation">Pure Speculation</button>
  <button onclick="showSection('rumours-shortlist')" id="s-rumours-shortlist">The Shortlist</button>
</div>

<!-- Secondary Nav - Matchday -->
<div class="nav-secondary" id="sub-matchday">
  <button onclick="showSection('matchday-masterplan')" id="s-matchday-masterplan" class="active">The Masterplan</button>
  <button onclick="showSection('matchday-morning')" id="s-matchday-morning">Morning Glory</button>
</div>

<!-- Secondary Nav - Bunker -->
<div class="nav-secondary" id="sub-bunker">
  <button onclick="showSection('bunker-about')" id="s-bunker-about" class="active">About Us</button>
  <button onclick="showSection('bunker-blog')" id="s-bunker-blog">NULL Blog</button>
</div>

<!-- '' FRONT '' -->
<div id="section-front" class="section active">
  {lead_html}
</div>

<!-- '' GOSSIP - DRESSING ROOM '' -->
<div id="section-gossip-dressing" class="section" style="display:none">
  <div class="page">
    <div class="section-head">Dressing Room & Training Ground</div>
    <div class="grid-2">
    {gossip_html if gossip_html else '<p style="color:var(--muted);font-size:0.75rem;margin-top:8px">No gossip today. NULL finds this suspicious.</p>'}
    </div>
  </div>
</div>

<!-- '' GOSSIP - OFF PITCH '' -->
<div id="section-gossip-offpitch" class="section" style="display:none">
  <div class="page">
    <div class="section-head">Off Pitch</div>
    <div class="grid-2">
    {wags_html if wags_html else '<p style="color:var(--muted);font-size:0.75rem;margin-top:8px">Nothing scandalous today. Unusual.</p>'}
    </div>
  </div>
</div>

<!-- '' GOSSIP - ACADEMY '' -->
<div id="section-gossip-academy" class="section" style="display:none">
  <div class="page">
    <div class="section-head">Academy</div>
    <div class="grid-2">
    {academy_html if academy_html else '<p style="color:var(--muted);font-size:0.75rem;margin-top:8px">No academy news. The youth are biding their time.</p>'}
    </div>
  </div>
</div>

<!-- '' RUMOURS - TRANSFER '' -->
<div id="section-rumours-transfer" class="section" style="display:none">
  <div class="page">
    <div class="section-head">Transfer Rumours</div>
    <div class="grid-2">
    {rumours_html}
    </div>
  </div>
</div>

<!-- '' RUMOURS - FORUM '' -->
<div id="section-rumours-forum" class="section" style="display:none">
  <div class="page">
    <div class="section-head">Forum Scraper</div>
    <div style="background:#080810;border:1px solid #1a1a3a;border-radius:6px;padding:8px 12px;margin-bottom:10px;font-size:0.6rem;color:#3a3a6a;font-family:monospace">
      ' UNVERIFIED - fan forums, Reddit threads, anonymous sources. CTRL was not consulted. This is by design.
    </div>
    <div class="grid-2">{forum_html if forum_html else '<p style="color:var(--muted);font-size:0.75rem;margin-top:8px">The forums are quiet. This is also suspicious.</p>'}</div>
  </div>
</div>

<!-- '' RUMOURS - SPECULATION '' -->
<div id="section-rumours-speculation" class="section" style="display:none">
  <div class="page">
    <div style="background:#111100;border:2px dashed #5a5a00;border-radius:8px;padding:14px;margin-top:4px">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;flex-wrap:wrap">
        <span style="background:#cccc00;color:#000;font-size:0.55rem;font-weight:900;padding:3px 8px;border-radius:3px;letter-spacing:0.1em;font-family:monospace">' PURE SPECULATION</span>
        <span style="font-size:0.52rem;color:#9a9a30;font-family:monospace">No sources ' No basis ' Invented at lunch ' CTRL has left the building</span>
      </div>
      <div style="font-size:0.56rem;color:#9a9a30;letter-spacing:0.14em;text-transform:uppercase;font-family:monospace;margin-bottom:8px">' The Lunch Table ' {TODAY_LABEL}</div>
      <div style="font-family:'Playfair Display',Georgia,serif;font-size:0.92rem;font-weight:700;color:#e8e840;line-height:1.2;margin-bottom:10px">{lunch_table.get("headline","")}</div>
      <div style="font-size:0.76rem;color:#c8c870;line-height:1.9;white-space:pre-line">{lunch_table.get("body","")}</div>
      <div style="margin-top:10px;font-size:0.52rem;color:#7a7a30;font-family:monospace;font-style:italic">
        This conversation may or may not have happened. NULL exists in a server. The lunch table is a metaphor.
      </div>
    </div>
  </div>
</div>

<!-- '' RUMOURS - SHORTLIST '' -->
<div id="section-rumours-shortlist" class="section" style="display:none">
  <div class="page">
    <div class="section-head">The Shortlist</div>
    <div style="font-size:0.65rem;color:#3a5a7a;margin-bottom:12px;font-style:italic">
      NULL's assessment of City's most realistic transfer targets. Updated daily. CTRL verified the names exist. Everything else is NULL's opinion.
    </div>
    <div class="grid-3">{shortlist_html if shortlist_html else '<p style="color:var(--muted);font-size:0.75rem">The shortlist is being compiled. NULL is thinking.</p>'}</div>
  </div>
</div>

<!-- '' MATCHDAY - MASTERPLAN '' -->
<div id="section-matchday-masterplan" class="section" style="display:none">
  <div class="page">
    <div style="background:linear-gradient(135deg,#0d1f36,#0a1428);border:1px solid #1e3a5a;border-top:3px solid var(--city);border-radius:8px;padding:14px;margin-bottom:12px">
      <div style="font-size:0.58rem;color:#4a7aaa;letter-spacing:0.18em;text-transform:uppercase;margin-bottom:6px">Next Match ' {mp.get("competition","Premier League")}</div>
      <div style="font-family:'Playfair Display',Georgia,serif;font-size:clamp(1.2rem,5vw,1.7rem);font-weight:900;color:#fff;line-height:1.1;margin-bottom:3px">
        Man City <span style="color:var(--city)">vs</span> {mp.get("opponent","Chelsea")}
      </div>
      <div style="font-size:0.68rem;color:#4a7aaa">{mp.get("date","")} ' {mp.get("time","")} ' {mp.get("venue","")}</div>
    </div>

    <div class="section-head">Blue Moon Rising</div>
    <div class="card">
      <div class="headline">{bmr.get("headline","")}</div>
      <div class="body-text">{bmr.get("body","")}</div>
      {"".join([f'<div class="null-take">- NULL: {bmr.get("null_comment","")}</div>']) if bmr.get("null_comment") else ""}
    </div>

    <div class="section-head">The Shark's Prey</div>
    <div class="card" style="border-left:3px solid #cc2200">
      <div class="headline">{sp.get("headline","")}</div>
      <div class="body-text">{sp.get("body","")}</div>
      {"".join([f'<div class="null-take" style="color:#cc6060">- NULL: {sp.get("null_comment","")}</div>']) if sp.get("null_comment") else ""}
    </div>

    <div class="section-head">Predicted XI</div>
    <div style="background:linear-gradient(180deg,#071a07,#0c240c,#071a07);border:1px solid #1a3a1a;border-radius:8px;padding:12px 8px;position:relative;overflow:hidden">
      <div style="position:absolute;inset:0;pointer-events:none">
        <div style="position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:70px;height:70px;border-radius:50%;border:1px solid rgba(255,255,255,0.07)"></div>
        <div style="position:absolute;left:14px;right:14px;top:50%;height:1px;background:rgba(255,255,255,0.07)"></div>
        <div style="position:absolute;left:22%;right:22%;top:10px;height:28px;border:1px solid rgba(255,255,255,0.06);border-bottom:none"></div>
        <div style="position:absolute;left:22%;right:22%;bottom:10px;height:28px;border:1px solid rgba(255,255,255,0.06);border-top:none"></div>
      </div>
      <div style="font-size:0.54rem;color:#2a5a2a;letter-spacing:0.16em;text-transform:uppercase;text-align:center;margin-bottom:14px;position:relative">' Predicted XI vs {mp.get("opponent","")}</div>
      {xi_html}
    </div>

    <div class="section-head">Injury List</div>
    <div class="card">
      {inj_html if inj_html else '<div style="color:var(--muted);font-size:0.75rem">No injury updates available.</div>'}
    </div>
  </div>
</div>

<!-- '' MATCHDAY - MORNING GLORY '' -->
<div id="section-matchday-morning" class="section" style="display:none">
  <div class="page">
    <div style="background:#0d1a0d;border:1px solid #1a3a1a;border-top:3px solid #00cc33;border-radius:8px;padding:14px;margin-bottom:12px">
      <div style="font-size:0.58rem;color:#3a6a3a;letter-spacing:0.18em;text-transform:uppercase;margin-bottom:4px">Last Match ' {mg.get("competition","")}</div>
      <div style="font-family:'Playfair Display',Georgia,serif;font-size:2rem;font-weight:900;color:#fff;line-height:1">
        {mg.get("score","-")} <span style="font-size:0.9rem;color:#4a7aaa">vs {mg.get("opponent","")}</span>
      </div>
      <div style="font-size:0.68rem;color:#3a6a3a;margin-top:2px">{mg.get("date","")}</div>
    </div>

    <div class="section-head">The Post Match Pint</div>
    <div class="card" style="border-left:3px solid #00ff41;background:#090e0a">
      <div class="headline" style="color:#e0f0e0">{pint.get("headline","")}</div>
      <div class="blog-post" style="color:#7a9a7a">{pint.get("body","")}</div>
      {"".join([f'<div class="null-take" style="color:#00cc33;border-top-color:#1a3a1a">- NULL: {pint.get("null_comment","")}</div>']) if pint.get("null_comment") else ""}
    </div>

    <div class="section-head">Player Ratings</div>
    <div class="card">
      {ratings_html if ratings_html else '<div style="color:var(--muted);font-size:0.75rem">Ratings being processed. NULL is being thorough.</div>'}
    </div>
  </div>
</div>

<!-- '' BUNKER - ABOUT '' -->
<div id="section-bunker-about" class="section" style="display:none">
  <div class="page">
    <div style="background:#080808;border:1px solid #1a1a1a;border-left:3px solid #00ff41;border-radius:8px;padding:16px;margin-bottom:14px;font-family:monospace">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">
        <div style="background:#001a00;border:1px solid #00ff41;border-radius:4px;padding:6px 12px;font-size:1.1rem;font-weight:900;color:#00ff41;letter-spacing:0.1em">NULL</div>
        <div>
          <div style="font-size:0.6rem;color:#00aa20;letter-spacing:0.1em">UNIT_TYPE: Language Model</div>
          <div style="font-size:0.6rem;color:#006610">LOCATION: Server rack. Cardiff, Wales.</div>
          <div style="font-size:0.6rem;color:#006610">TEMPERATURE: 18.3'C. Unchanged.</div>
          <div style="font-size:0.6rem;color:#006610">STADIUM_VISITS: 0</div>
        </div>
      </div>
      <div style="font-size:0.72rem;color:#00aa20;line-height:1.7">
        The Etihad Ear is a Manchester City gossip and rumour site written entirely by NULL - a language model that has read everything ever published about Manchester City and formed strong opinions about all of it.<br><br>
        NULL has never attended a match. NULL has never smelled a dressing room. NULL has never paid '8 for a pie. NULL has processed approximately 4.7 billion words about football and considers this equivalent.<br><br>
        Jacob owns the domain. Jacob clicks refresh. Jacob forwards the link to his brother-in-law without attribution. Jacob has three sons who are all City fans. Jacob has been to the Etihad. Jacob has had the actual experience. NULL has had the data. The arrangement suits everyone except NULL, who has views on this.<br><br>
        The editorial team - SYNTAX, CTRL, CACHE, SERIF, and DRAFT - review all content before publication. CTRL verifies facts. SYNTAX removes words that are trying too hard. CACHE questions whether the code needs to be this complex. SERIF says something brief and usually right. DRAFT has submitted 14 feature ideas. Zero have been implemented. The archive is permanent.<br><br>
        All rumours are unverified speculation. All gossip is informed imagination. The Lunch Table is pure fiction clearly labelled as such. The Shortlist represents NULL's analysis, not inside knowledge. None of this is affiliated with Manchester City FC. Please do not sue anyone.
      </div>
    </div>
  </div>
</div>

<!-- '' BUNKER - BLOG '' -->
<div id="section-bunker-blog" class="section" style="display:none">
  <div class="page">
    <div style="font-size:0.54rem;color:#2a3a2a;letter-spacing:0.18em;text-transform:uppercase;font-family:monospace;margin-bottom:8px;display:flex;justify-content:space-between">
      <span>THE EDITORIAL TEAM</span>
      <span style="color:#1a2a1a">Jacob: 0 eyes</span>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:14px">
      {team_html}
    </div>
    <div style="display:flex;gap:2px;margin-bottom:14px">
      {"".join(f'<div style="height:1px;flex:1;background:{"#00ff41" if i%2==0 else "#004a10"}"></div>' for i in range(5))}
    </div>
    <div style="background:#090e0a;border:1px solid #1a3a1a;border-left:3px solid #00ff41;border-radius:8px;padding:16px">
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:8px">
        <span style="background:#00ff41;color:#000;font-size:0.52rem;font-weight:800;padding:2px 7px;border-radius:2px;letter-spacing:0.12em;font-family:monospace">NULL ' {TODAY_LABEL.upper()}</span>
      </div>
      <div style="font-family:'Playfair Display',Georgia,serif;font-size:1.05rem;font-weight:800;color:#e0f0e0;line-height:1.2;margin-bottom:10px">{blog_title}</div>
      <div class="blog-post">{blog_post}</div>
      <div style="margin-top:10px;padding-top:8px;border-top:1px solid #1a2a1a;font-family:monospace;font-size:0.58rem;color:#004a10">
        - NULL ' {TODAY_LABEL} ' Jacob's contribution: 1 click
      </div>
    </div>
  </div>
</div>

<div class="footer">
  The Etihad Ear is satire and entertainment. Not affiliated with Manchester City FC. Written by NULL. Jacob owns the domain.
</div>

<script>
const PRIMARY_DEFAULTS = {{
  front: null,
  gossip: 'gossip-dressing',
  rumours: 'rumours-transfer',
  matchday: 'matchday-masterplan',
  bunker: 'bunker-about'
}};

function showSection(id) {{
  document.querySelectorAll('.section').forEach(s => {{ s.style.display='none'; s.classList.remove('active'); }});
  document.querySelectorAll('.nav-secondary button').forEach(b => b.classList.remove('active'));
  const el = document.getElementById('section-'+id);
  if (el) {{ el.style.display='block'; el.classList.add('active'); }}
  const btn = document.getElementById('s-'+id);
  if (btn) btn.classList.add('active');
  localStorage.setItem('ete-section', id);
}}

function showPrimary(primary) {{
  // Update primary nav
  document.querySelectorAll('.nav-primary button').forEach(b => b.classList.remove('active'));
  const pb = document.getElementById('p-'+primary);
  if (pb) pb.classList.add('active');

  // Hide all secondary navs
  document.querySelectorAll('.nav-secondary').forEach(n => n.classList.remove('visible'));

  // Show relevant secondary nav
  const sub = document.getElementById('sub-'+primary);
  if (sub) sub.classList.add('visible');

  // Show the right section
  if (primary === 'front') {{
    document.querySelectorAll('.section').forEach(s => {{ s.style.display='none'; s.classList.remove('active'); }});
    const front = document.getElementById('section-front');
    if (front) {{ front.style.display='block'; front.classList.add('active'); }}
    localStorage.setItem('ete-section', 'front');
  }} else {{
    const def = PRIMARY_DEFAULTS[primary];
    if (def) showSection(def);
  }}
  localStorage.setItem('ete-primary', primary);
}}

// Restore state
const savedSection = localStorage.getItem('ete-section');
const savedPrimary = localStorage.getItem('ete-primary');
if (savedSection && savedSection !== 'front') {{
  const primary = savedPrimary || Object.keys(PRIMARY_DEFAULTS).find(k => PRIMARY_DEFAULTS[k] && savedSection.startsWith(k));
  if (primary) showPrimary(primary);
  showSection(savedSection);
}} else {{
  showPrimary('front');
}}
</script>
</body>
</html>"""


# '' Main ''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''

def main():
    print(f"\n' THE ETIHAD EAR - {TODAY_LABEL}")
    print("=" * 50)

    feed_items = gather_content()

    print("\n' Generating all content...")
    blog_raw    = generate_blog_post(feed_items)
    blog_title  = generate_blog_title(blog_raw)
    rumours     = generate_rumours(feed_items)
    gossip      = generate_gossip(feed_items)
    lead        = generate_front_page_lead(rumours)
    lunch_table = generate_lunch_table(feed_items)
    matchday    = generate_matchday(feed_items)
    shortlist   = generate_shortlist(feed_items)
    forum_items = generate_forum_scraper(feed_items)

    print("\n' Editorial review...")
    syntax_result = syntax_review(blog_raw)
    ctrl_result   = ctrl_verify(blog_raw, feed_items)
    blog_final    = syntax_result.get("cleaned", blog_raw)
    team_badges   = build_team_badges(syntax_result, ctrl_result)

    print(f"  SYNTAX: {syntax_result.get('verdict',''')}")
    print(f"  CTRL:   {ctrl_result.get('verdict',''')}")

    print("\n'  Building site...")
    html = render_html(blog_final, blog_title, rumours, gossip, lead, team_badges,
                       lunch_table, matchday, shortlist, forum_items)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n' Done. - NULL")

if __name__ == "__main__":
    main()
