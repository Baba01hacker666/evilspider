import asyncio
import aiohttp
import json
import os
import re
import sys
import logging
from urllib.parse import urlparse, urljoin

class Crawler:
    def __init__(self, config):
        self.config = config.config
        self.visited = set()
        self.results = []
        self.semaphore = asyncio.Semaphore(self.config.get('threads', 10))
        self.queue = asyncio.Queue()
        self.subdomains = set()

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

    async def parse_robots_txt(self, session):
        if not self.config.get('robots'):
            return
        parsed_url = urlparse(self.config['url'])
        robots_url = f"{parsed_url.scheme}://{parsed_url.netloc}/robots.txt"
        logging.info(f"Parsing robots.txt: {robots_url}")
        try:
            async with session.get(robots_url, timeout=self.config['timeout'], ssl=False) as response:
                if response.status == 200:
                    text = await response.text()
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
            async with session.get(sitemap_url, timeout=self.config['timeout'], ssl=False) as response:
                if response.status == 200:
                    text = await response.text()
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
        # print(f'Fetching: {url}')
        if url in self.visited:
            return []
        self.visited.add(url)

        async with self.semaphore:
            try:
                async with session.get(url, timeout=self.config['timeout'], ssl=False) as response:
                    status = response.status
                    text = await response.text()

                    # 1. Check Status Code
                    if status in self.config['status']:
                        # 2. Check Extensions & Keywords
                        if self.check_extension(url) and self.contains_keywords(text):
                            # Detect file uploads
                            has_upload = False
                            if self.config.get('detect_uploads'):
                                if re.search(r'<input[^>]+type=["\']file["\']', text, re.I):
                                    has_upload = True

                            # 3. Check Parameters
                            if not self.config['params_only'] or self.is_parameterized(url):
                                result_entry = {"url": url, "status": status}
                                if has_upload:
                                    result_entry["has_upload"] = True

                                if self.config['json']:
                                    sys.stdout.write(json.dumps(result_entry) + "\n")
                                    sys.stdout.flush()
                                else:
                                    if not self.config['quiet']:
                                        if has_upload:
                                            sys.stdout.write(f"[+] [{status}] Found Upload Form: {url}\n")
                                        else:
                                            sys.stdout.write(f"[+] [{status}] Found: {url}\n")
                                        sys.stdout.flush()
                                self.results.append(result_entry)

                    clean_links = []
                    # Always extract links on 200 or 404 (to find hidden endpoints)
                    if status in self.config['status'] or status == 404:
                        # Extract links (Absolute and Relative) from href and src
                        raw_links = list(set(re.findall(r'(?:href|src)=["\'](.*?)["\']', text)))

                        for link in raw_links:
                            full_url = urljoin(url, link)

                            target_netloc = urlparse(self.config['url']).netloc
                            found_netloc = urlparse(full_url).netloc

                            target_domain = target_netloc.split(':')[0]
                            found_domain = found_netloc.split(':')[0]

                            is_subdomain = found_domain != target_domain and found_domain.endswith('.' + target_domain)

                            if is_subdomain:
                                if found_domain not in self.subdomains:
                                    self.subdomains.add(found_domain)
                                    if not self.config['quiet']:
                                        logging.info(f"Discovered subdomain: {found_domain}")

                            # Keep it in scope (basic implementation, can be customized)
                            if found_domain == target_domain or is_subdomain:
                                clean_links.append(full_url)
                    return clean_links

            except aiohttp.ClientError as e:
                logging.debug(f"Network error for {url}: {e}")
                return []
            except asyncio.TimeoutError:
                logging.debug(f"Timeout for {url}")
                return []
            except Exception as e:
                logging.debug(f"Unexpected error for {url}: {e}")
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
