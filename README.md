# The Etihad Ear

Manchester City gossip, rumours & what no one else dares print.
Written entirely by **NULL**. Jacob owns the domain. This is the arrangement.

**Live site:** `https://YOUR_USERNAME.github.io/etihad-ear`

---

## How it works

Every morning at 07:00 CET the system:

1. **Gathers content** from 12+ sources — Sky Sports, Romano RSS, BBC Sport, MEN, r/MCFC, r/footballtransfers, Marca, AS and more
2. **NULL writes** today's blog post, rumours and gossip via Claude API
3. **The editorial team reviews** — SYNTAX (language), CTRL (facts), CACHE (tech), SERIF (design), DRAFT (suggestions nobody asked for)
4. **GitHub Pages deploys** the updated site automatically
5. **Jacob clicks refresh.** This is Jacob's contribution.

---

## Setup

### 1. Create a public GitHub repo named `etihad-ear`

### 2. Upload these three files:
```
generate.py
.github/workflows/deploy.yml
README.md
```

### 3. Add API key secret
Settings → Secrets and variables → Actions → New repository secret
- Name: `ANTHROPIC_API_KEY`
- Value: your key from console.anthropic.com

### 4. Enable GitHub Pages
Settings → Pages → Source: Deploy from branch → main → / (root)

### 5. First run
Actions → The Etihad Ear — Daily Update → Run workflow

Wait 3-4 minutes. Site is live.

---

## The team

| Name | Role | Notes |
|------|------|-------|
| NULL | Editor-in-Chief | Writes everything |
| SYNTAX | Language Editor | Removes what NULL over-writes |
| CTRL | Fact Checker | No opinions. Only facts. |
| CACHE | Tech Editor | "Could be simpler." Always. |
| SERIF | Design Editor | One sentence. Usually right. |
| DRAFT | Junior Editor | 14 suggestions. 0 implemented. |
| JACOB | Owner | Clicks refresh |

---

## Cost
- GitHub Pages + Actions: Free
- Claude API: ~£2-4/month
