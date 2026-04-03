import asyncio
import aiohttp
import json
import os
import re
import sys
import logging
import posixpath
import random
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlparse, urljoin, urlsplit, urlunsplit

class Crawler:
    def __init__(self, config):
        self.config = config.config
        self.visited = set()
        self.results = []
        self.semaphore = asyncio.Semaphore(self.config.get('threads', 10))
        self.queue = asyncio.Queue()
        self.subdomains = set()
        self.target_domain = urlparse(self.config['url']).netloc.split(':')[0].lower()

    class LinkExtractor(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.links = set()

        def handle_starttag(self, tag, attrs):
            attrs_dict = dict(attrs)
            for attr in ("href", "src", "action", "data"):
                value = attrs_dict.get(attr)
                if value:
                    self.links.add(value.strip())
            if tag == "meta":
                http_equiv = attrs_dict.get("http-equiv", "").lower()
                content = attrs_dict.get("content", "")
                if http_equiv == "refresh":
                    m = re.search(r'url\s*=\s*([^;]+)', content, flags=re.I)
                    if m:
                        self.links.add(m.group(1).strip(" '\""))
            if tag == "link":
                rel = attrs_dict.get("rel", "")
                rel_tokens = rel if isinstance(rel, list) else rel.split()
                if "canonical" in [token.lower() for token in rel_tokens]:
                    href = attrs_dict.get("href")
                    if href:
                        self.links.add(href.strip())
            if tag == "source":
                srcset = attrs_dict.get("srcset")
                if srcset:
                    for item in srcset.split(","):
                        candidate = item.strip().split(" ")[0]
                        if candidate:
                            self.links.add(candidate)

    def check_extension(self, url):
        """Hunts for specific file extensions."""
        if not self.config['exts']:
            return True # If no exts specified, allow all
        parsed_path = urlparse(url).path.lower()
        return any(parsed_path.endswith(f".{ext.strip('.')}") for ext in self.config['exts'])

    def contains_keywords(self, text):
        if not self.config['keywords']:
            return True
        return any(word.lower() in text.lower() for word in self.config['keywords'])

    def is_parameterized(self, url):
        return bool(urlparse(url).query)

    def normalize_url(self, raw_url, base_url=None):
        if not raw_url:
            return None
        full_url = urljoin(base_url or self.config['url'], raw_url.strip())
        parsed = urlsplit(full_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return None

        netloc = parsed.netloc.lower()
        if ":" in netloc:
            host, port = netloc.rsplit(":", 1)
            if (parsed.scheme == "http" and port == "80") or (parsed.scheme == "https" and port == "443"):
                netloc = host

        path = parsed.path or "/"
        path = re.sub(r"/{2,}", "/", path)
        norm_path = posixpath.normpath(path)
        if not norm_path.startswith("/"):
            norm_path = f"/{norm_path}"
        if path.endswith("/") and norm_path != "/":
            norm_path = f"{norm_path}/"

        query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
        query = urlencode(sorted(query_pairs), doseq=True)
        return urlunsplit((parsed.scheme.lower(), netloc, norm_path, query, ""))

    def _is_in_scope(self, full_url):
        parsed = urlparse(full_url)
        found_domain = parsed.netloc.split(':')[0].lower()
        is_subdomain = found_domain != self.target_domain and found_domain.endswith('.' + self.target_domain)
        if is_subdomain and found_domain not in self.subdomains:
            self.subdomains.add(found_domain)
            if not self.config['quiet']:
                logging.info(f"Discovered subdomain: {found_domain}")
        return found_domain == self.target_domain or is_subdomain

    def extract_links(self, base_url, text):
        if not text:
            return []
        extractor = self.LinkExtractor()
        recovered_links = set()
        try:
            extractor.feed(text)
        except Exception:
            logging.debug(f"HTML parser recovery failed for {base_url}; using regex fallback.")
        recovered_links.update(extractor.links)

        regex_patterns = [
            r'(?:href|src|action)=["\'](.*?)["\']',
            r'window\.location(?:\.href)?\s*=\s*["\'](.*?)["\']',
            r'fetch\(["\'](.*?)["\']',
            r'axios\.(?:get|post|put|patch|delete)\(["\'](.*?)["\']'
        ]
        for pattern in regex_patterns:
            recovered_links.update(re.findall(pattern, text, flags=re.I))

        clean_links = []
        for link in recovered_links:
            full_url = self.normalize_url(link, base_url=base_url)
            if full_url and self._is_in_scope(full_url):
                clean_links.append(full_url)
        return list(set(clean_links))

    async def _read_text_body(self, response):
        content_type = response.headers.get("Content-Type", "").lower()
        allowed_content_types = (
            "text/",
            "application/json",
            "application/xml",
            "application/xhtml+xml",
            "application/javascript",
            "application/x-javascript"
        )
        if content_type and not any(token in content_type for token in allowed_content_types):
            return None

        max_body_bytes = self.config.get("max_body_bytes")
        content_length = response.content_length
        if max_body_bytes and content_length and content_length > max_body_bytes:
            logging.debug(f"Skipping large body ({content_length} bytes): {response.url}")
            return None

        try:
            raw = await response.content.read(max_body_bytes + 1 if max_body_bytes else -1)
            if max_body_bytes and len(raw) > max_body_bytes:
                logging.debug(f"Skipping oversized streamed body (> {max_body_bytes} bytes): {response.url}")
                return None
            encoding = response.charset or "utf-8"
            return raw.decode(encoding, errors="replace")
        except Exception as e:
            logging.debug(f"Failed decoding body for {response.url}: {e}")
            return None

    async def parse_robots_txt(self, session):
        if not self.config.get('robots'):
            return
        parsed_url = urlparse(self.config['url'])
        robots_url = f"{parsed_url.scheme}://{parsed_url.netloc}/robots.txt"
        logging.info(f"Parsing robots.txt: {robots_url}")
        try:
            async with session.get(robots_url, timeout=self.config['timeout'], ssl=False, proxy=self.config.get('proxy')) as response:
                if response.status == 200:
                    text = await response.text(errors="replace")
                    urls = []
                    for line in text.splitlines():
                        line = line.strip()
                        if line.lower().startswith('allow:') or line.lower().startswith('disallow:'):
                            path = line.split(':', 1)[1].strip()
                            if path:
                                urls.append(urljoin(self.config['url'], path))
                        elif line.lower().startswith('sitemap:'):
                            sitemap_url = line.split(':', 1)[1].strip()
                            if self.config.get('sitemaps'):
                                await self.parse_sitemap(session, sitemap_url)
                    for u in urls:
                        await self.queue.put((u, 1))
                        if not self.config['quiet']:
                            logging.info(f"Added from robots.txt: {u}")
        except Exception as e:
            logging.debug(f"Could not fetch robots.txt: {e}")

    async def parse_sitemap(self, session, sitemap_url=None):
        if not self.config.get('sitemaps'):
            return
        if not sitemap_url:
            parsed_url = urlparse(self.config['url'])
            sitemap_url = f"{parsed_url.scheme}://{parsed_url.netloc}/sitemap.xml"
        logging.info(f"Parsing sitemap.xml: {sitemap_url}")
        try:
            async with session.get(sitemap_url, timeout=self.config['timeout'], ssl=False, proxy=self.config.get('proxy')) as response:
                if response.status == 200:
                    text = await response.text(errors="replace")
                    urls = re.findall(r'<loc>(.*?)</loc>', text)
                    for u in urls:
                        if u.endswith('.xml'):
                            await self.parse_sitemap(session, u)
                        else:
                            await self.queue.put((u, 1))
                            if not self.config['quiet']:
                                logging.info(f"Added from sitemap: {u}")
        except Exception as e:
            logging.debug(f"Could not fetch sitemap.xml: {e}")

    async def fetch(self, session, url):
        normalized_url = self.normalize_url(url)
        if not normalized_url:
            return []
        if normalized_url in self.visited:
            return []
        self.visited.add(normalized_url)

        async with self.semaphore:
            retries = max(0, self.config.get('retries', 0))
            for attempt in range(retries + 1):
                try:
                    timeout = aiohttp.ClientTimeout(
                        total=self.config.get('timeout'),
                        sock_connect=self.config.get('connect_timeout') or self.config.get('timeout'),
                        sock_read=self.config.get('read_timeout') or self.config.get('timeout')
                    )
                    async with session.get(
                        normalized_url,
                        timeout=timeout,
                        ssl=False,
                        proxy=self.config.get('proxy'),
                        allow_redirects=self.config.get('follow_redirects', True)
                    ) as response:
                        status = response.status
                        text = await self._read_text_body(response)

                        # 1. Check Status Code
                        if status in self.config['status']:
                            # 2. Check Extensions & Keywords
                            searchable_text = text or ""
                            if self.check_extension(normalized_url) and self.contains_keywords(searchable_text):
                                # Detect file uploads
                                has_upload = False
                                if self.config.get('detect_uploads') and text:
                                    if re.search(r'<input[^>]+type=["\']file["\']', searchable_text, re.I):
                                        has_upload = True

                                # 3. Check Parameters
                                if not self.config['params_only'] or self.is_parameterized(normalized_url):
                                    result_entry = {"url": normalized_url, "status": status}
                                    if has_upload:
                                        result_entry["has_upload"] = True
                                    if self.config.get("report_redirects"):
                                        redirects = [self.normalize_url(str(h.url)) for h in response.history]
                                        redirects = [r for r in redirects if r]
                                        if redirects:
                                            result_entry["redirect_chain"] = redirects

                                    if self.config['json']:
                                        sys.stdout.write(json.dumps(result_entry) + "\n")
                                        sys.stdout.flush()
                                    else:
                                        if not self.config['quiet']:
                                            if has_upload:
                                                sys.stdout.write(f"[+] [{status}] Found Upload Form: {normalized_url}\n")
                                            else:
                                                sys.stdout.write(f"[+] [{status}] Found: {normalized_url}\n")
                                            sys.stdout.flush()
                                    self.results.append(result_entry)

                        clean_links = []
                        # Always extract links on 200 or 404 (to find hidden endpoints)
                        if text and (status in self.config['status'] or status == 404):
                            clean_links = self.extract_links(normalized_url, text)
                        return clean_links

                except aiohttp.ClientError as e:
                    logging.debug(f"Network error for {normalized_url}: {e}")
                except asyncio.TimeoutError:
                    logging.debug(f"Timeout for {normalized_url}")
                except Exception as e:
                    logging.debug(f"Unexpected error for {normalized_url}: {e}")

                if attempt < retries:
                    base = max(0.0, self.config.get("retry_backoff", 0.5))
                    jitter = max(0.0, self.config.get("retry_jitter", 0.25))
                    delay = (base * (2 ** attempt)) + random.uniform(0, jitter)
                    await asyncio.sleep(delay)
            return []

    async def worker(self, session):
        while True:
            try:
                url, depth = await self.queue.get()
            except asyncio.CancelledError:
                break

            try:
                if len(self.visited) >= self.config['max_links']:
                    continue

                if depth <= self.config['max_depth']:
                    links = await self.fetch(session, url)
                    for link in links:
                        if link not in self.visited:
                            await self.queue.put((link, depth + 1))
            except Exception as e:
                logging.debug(f"Worker error processing {url}: {e}")
            finally:
                self.queue.task_done()

    async def crawl(self):
        logging.info(f"Starting EvilSpider on {self.config['url']}")
        logging.info(f"Threads: {self.config['threads']} | Exts: {self.config['exts']} | Status: {self.config['status']} | Max Depth: {self.config['max_depth']}")

        connector = aiohttp.TCPConnector(limit_per_host=self.config['threads'])
        headers = {"User-Agent": self.config['user_agent']}
        if self.config.get('parsed_headers'):
            headers.update(self.config['parsed_headers'])

        async with aiohttp.ClientSession(headers=headers, connector=connector, cookies=self.config.get('parsed_cookies')) as session:
            # Parse robots.txt and sitemap.xml first
            await self.parse_robots_txt(session)
            await self.parse_sitemap(session)

            await self.queue.put((self.config['url'], 1))

            workers = [asyncio.create_task(self.worker(session)) for _ in range(self.config['threads'])]

            await self.queue.join()

            for w in workers:
                w.cancel()

            if len(self.visited) >= self.config['max_links']: # Safety threshold
                logging.warning("Max limits reached.")

    def save_output(self):
        if self.results:
            try:
                with open(self.config['output'], 'w') as f:
                    json.dump(self.results, f, indent=4)
                logging.info(f"Saved {len(self.results)} targets to {self.config['output']}")
            except IOError as e:
                logging.error(f"Failed to save output to {self.config['output']}: {e}")
        if self.subdomains:
            logging.info(f"Discovered subdomains: {', '.join(self.subdomains)}")
            import os
            base, ext = os.path.splitext(self.config['output'])
            if not ext:
                ext = '.json'
            subdomains_output = f"{base}_subdomains{ext}"
            try:
                with open(subdomains_output, 'w') as f:
                    json.dump(list(self.subdomains), f, indent=4)
                logging.info(f"Saved {len(self.subdomains)} subdomains to {subdomains_output}")
            except IOError as e:
                logging.error(f"Failed to save subdomains to {subdomains_output}: {e}")
