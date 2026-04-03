# EvilSpider

Async attack-surface crawler for recon. Finds parameterized URLs, hidden paths from robots/sitemaps, file-upload forms, and in-scope subdomains.

## Features
- Async crawling with configurable concurrency
- robots.txt and sitemap.xml parsing
- Extension filtering (`php,bak,env,txt`)
- Keyword matching in response bodies
- Parameterized URL detection
- File upload form detection
- Cookies, headers, proxies, custom User-Agent
- In-scope subdomain discovery
- JSON output

## Why it exists
Most crawlers focus on breadth. EvilSpider is built for recon workflows where you care about:
- hidden endpoints
- upload surfaces
- parameterized routes
- extra in-scope assets

## Install
```bash
git clone https://github.com/Baba01hacker666/evilspider.git
cd evilspider
pip install -r requirements.txt
