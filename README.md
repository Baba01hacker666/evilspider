# EvilSpider

Async attack-surface crawler for recon. EvilSpider prioritizes useful findings (hidden paths, parameterized endpoints, upload forms, in-scope subdomains) over generic breadth-first crawling.

## Features
- Async crawling with configurable concurrency
- URL normalization before dedupe (query ordering, fragments, relative/absolute forms)
- robots.txt and sitemap.xml parsing
- Broader link extraction from HTML tags (`href`, `src`, `action`, meta refresh, canonical, `srcset`) plus JS regex fallbacks
- Retry + exponential backoff + jitter
- Optional redirect-chain reporting
- Separate connect/read timeout controls
- Content-type/body-size gating to avoid binary or oversized body parsing
- Extension and keyword filtering
- Parameterized URL detection
- File upload form detection
- Cookies, custom headers, proxies, custom User-Agent
- In-scope subdomain discovery
- JSON output

## Install
```bash
git clone https://github.com/Baba01hacker666/evilspider.git
cd evilspider
pip install aiohttp
```

## Quick start
```bash
python main.py crawl -u https://example.com
```

## High-value recon workflows

### 1) Hidden endpoint hunt
```bash
python main.py crawl \
  -u https://target.tld \
  -s 200,403,404 \
  --robots --sitemaps \
  -d 4
```

### 2) Upload surface hunt
```bash
python main.py crawl \
  -u https://target.tld \
  --detect-uploads \
  -k upload,file,multipart \
  -s 200,403
```

### 3) Authenticated crawl with cookies
```bash
python main.py crawl \
  -u https://target.tld \
  -C 'session=abc123; role=admin' \
  -H 'X-Requested-With: EvilSpider'
```

### 4) Proxied Burp crawl
```bash
python main.py crawl \
  -u https://target.tld \
  -x http://127.0.0.1:8080 \
  --follow-redirects \
  --report-redirects
```

### 5) 403/200 recon mode
```bash
python main.py crawl \
  -u https://target.tld \
  -s 200,403 \
  -e php,bak,env \
  -p
```

## Common options
- `-u, --url`: Target URL
- `-t, --threads`: Concurrent requests
- `-d, --max-depth`: Crawl depth
- `-m, --max-links`: Safety cap
- `-s, --status`: Interesting status codes
- `-e, --exts`: Extension focus list
- `-k, --keywords`: Body keyword filter
- `-p, --params-only`: Only flag URLs with query params
- `--robots`, `--sitemaps`: Seed discovery from robots/sitemaps
- `--detect-uploads`: Mark pages that include `<input type="file">`
- `--retries`, `--retry-backoff`, `--retry-jitter`: Retry strategy tuning
- `--connect-timeout`, `--read-timeout`, `-T/--timeout`: Timeout tuning
- `--max-body-bytes`: Skip very large response bodies
- `--follow-redirects`, `--report-redirects`: Redirect strategy/reporting
- `-C, --cookies`: Cookie string or cookie file
- `-H, --headers`: Add request headers (repeatable)
- `-x, --proxy`: Proxy URL
- `-j, --json`: Stream findings as JSON lines
- `-o, --output`: File to write final JSON findings

## Use Cases

- Bug bounty reconnaissance
- Attack surface discovery
- OSINT crawling
- Hidden endpoint enumeration
