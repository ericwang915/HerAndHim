---
name: summarize
description: "Summarize or extract text from URLs, articles, PDFs, and local files. Use when: user asks to summarize a link, article, web page, or document, or asks 'what is this link about?'. NOT for: YouTube transcripts (use youtube skill), full document editing, or real-time news (use news skill)."
dependencies: requests, beautifulsoup4
metadata:
  emoji: "🧾"
---

# Summarize

Extract and summarise content from URLs, articles, and local files.

## When to Use

✅ **USE this skill when:**

- "Summarize this article/URL"
- "What's this link about?"
- "Give me the key points from this page"
- "TL;DR this document"
- "Extract the main content from this URL"

## When NOT to Use

❌ **DON'T use this skill when:**

- YouTube video transcripts → use `youtube` skill
- Real-time news search → use `news` skill
- PDF text extraction → use `pdf_reader` skill
- Web search for information → use `tavily_search` or `web_search` tool

## Usage

Scripts run through the `run_skill_script` tool — pass the script path and an argv list (one item per argument, no shell quoting). Never try to run them with `run_command`.

### Summarize a URL

```
run_skill_script(script="{skill_path}/summarize_url.py", args=["https://example.com/article"])
```

### Options

```
# Short summary (default)
run_skill_script(script="{skill_path}/summarize_url.py", args=["https://example.com", "--length", "short"])

# Detailed summary
run_skill_script(script="{skill_path}/summarize_url.py", args=["https://example.com", "--length", "long"])

# Extract text only (no summarization)
run_skill_script(script="{skill_path}/summarize_url.py", args=["https://example.com", "--extract-only"])

# JSON output
run_skill_script(script="{skill_path}/summarize_url.py", args=["https://example.com", "--format", "json"])
```

### Quick Alternative (curl + readability)

Only when the `run_command` shell tool is available (it is off on
network-exposed installs) — for simple text extraction without the script:

```bash
curl -sL "https://example.com" | python -c "
import sys
from html.parser import HTMLParser
class S(HTMLParser):
    def __init__(s): super().__init__(); s.t=[]; s.skip={'script','style','nav','footer','header'}; s.s=set()
    def handle_starttag(s,t,a): (s.s.add(t) if t in s.skip else None)
    def handle_endtag(s,t): s.s.discard(t)
    def handle_data(s,d): (s.t.append(d.strip()) if not s.s and d.strip() else None)
p=S(); p.feed(sys.stdin.read()); print('\n'.join(p.t[:100]))
"
```

## Notes

- Requires `requests` and `beautifulsoup4` (installed by default)
- Some sites block automated access — try adding a User-Agent header
- For paywalled content, the script can only extract freely available text
- Large pages are truncated to avoid context overflow

## Resources

| File | Description |
|------|-------------|
| `summarize_url.py` | Fetch, extract, and summarise web page content |
