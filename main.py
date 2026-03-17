import asyncio
import aiohttp
import argparse
import json
import os
import re
from urllib.parse import urlparse, urljoin

class EvilSpider:
    def __init__(self, args):
        self.config = self._build_config(args)
        self.visited = set()
        self.results = []
        # Semaphore limits concurrent async tasks to avoid crashing the network/host
        self.semaphore = asyncio.Semaphore(self.config.get('threads', 10))

    def _build_config(self, args):
        """Merges CLI args with an optional config file. CLI overrides Config."""
        config = {
            "url": None,
            "threads": 10,
            "timeout": 5,
            "params_only": False,
            "status": [200],
            "keywords": [],
            "exts": [],
            "user_agent": "EvilSpider/2.0 (Customizable Crawler)"
        }
        
        # Load config file if specified and exists
        if args.config and os.path.exists(args.config):
            with open(args.config, 'r') as f:
                file_config = json.load(f)
                config.update(file_config)
                
        # Override with CLI arguments (if provided)
        cli_args = {k: v for k, v in vars(args).items() if v is not None}
        config.update(cli_args)
        
        # Ensure lists are properly typed if passed as strings from CLI
        if isinstance(config['status'], str):
            config['status'] = [int(s.strip()) for s in config['status'].split(',')]
        if isinstance(config['keywords'], str):
            config['keywords'] = [k.strip() for k in config['keywords'].split(',')]
        if isinstance(config['exts'], str):
            config['exts'] = [e.strip() for e in config['exts'].split(',')]
            
        return config

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

    async def fetch(self, session, url):
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
                            # 3. Check Parameters
                            if not self.config['params_only'] or self.is_parameterized(url):
                                print(f"[+] [{status}] Found: {url}")
                                self.results.append({"url": url, "status": status})

                    # Extract links (Absolute and Relative)
                    raw_links = re.findall(r'href=["\'](.*?)["\']', text)
                    clean_links = []
                    for link in raw_links:
                        full_url = urljoin(url, link)
                        # Keep it in scope (basic implementation, can be customized)
                        if urlparse(full_url).netloc == urlparse(self.config['url']).netloc:
                            clean_links.append(full_url)
                    return clean_links

            except Exception as e:
                # Silently pass timeouts/errors to maintain speed
                return []

    async def crawl(self):
        if not self.config.get('url'):
            print("[-] No target URL provided. Use -u or specify in config.")
            return

        print(f"[*] Starting EvilSpider on {self.config['url']}")
        print(f"[*] Threads: {self.config['threads']} | Exts: {self.config['exts']} | Status: {self.config['status']}")
        
        connector = aiohttp.TCPConnector(limit_per_host=self.config['threads'])
        headers = {"User-Agent": self.config['user_agent']}
        
        async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
            queue = [self.config['url']]
            
            while queue:
                tasks = [self.fetch(session, url) for url in queue]
                queue = []
                responses = await asyncio.gather(*tasks)
                
                for links in responses:
                    for link in links:
                        if link not in self.visited:
                            queue.append(link)
                
                if len(self.visited) > 5000: # Safety threshold
                    print("[!] Max limits reached.")
                    break

    def save_output(self):
        if self.results:
            with open('spider_results.json', 'w') as f:
                json.dump(self.results, f, indent=4)
            print(f"\n[*] Saved {len(self.results)} targets to spider_results.json")

def main():
    parser = argparse.ArgumentParser(description="EvilSpider - Fast Async Web Crawler")
    parser.add_argument("-u", "--url", help="Target URL to crawl")
    parser.add_argument("-c", "--config", help="Path to JSON config file (optional)")
    parser.add_argument("-t", "--threads", type=int, help="Number of concurrent threads/requests")
    parser.add_argument("-e", "--exts", help="Comma-separated extensions to hunt (e.g., php,bak,env,txt)")
    parser.add_argument("-s", "--status", help="Comma-separated HTTP status codes (e.g., 200,301,403)")
    parser.add_argument("-k", "--keywords", help="Comma-separated keywords to search in body")
    parser.add_argument("-p", "--params-only", action="store_true", help="Only flag URLs with parameters (?id=1)")
    
    args = parser.parse_args()
    
    # If no arguments provided at all, show help
    if not any(vars(args).values()):
        parser.print_help()
        return

    spider = EvilSpider(args)
    try:
        asyncio.run(spider.crawl())
    except KeyboardInterrupt:
        print("\n[!] User interrupted. Saving progress...")
    finally:
        spider.save_output()

if __name__ == "__main__":
    main()
