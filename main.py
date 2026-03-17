import asyncio
import aiohttp
import argparse
import json
import os
import re
import sys
import logging
from urllib.parse import urlparse, urljoin

class EvilSpiderConfig:
    def __init__(self, args_dict):
        self.config = {
            "url": None,
            "threads": 10,
            "timeout": 5,
            "params_only": False,
            "status": [200],
            "keywords": [],
            "exts": [],
            "user_agent": os.environ.get("EVILSPIDER_USER_AGENT", "EvilSpider/2.0 (Customizable Crawler)"),
            "max_links": 5000,
            "output": "spider_results.json",
            "json": False,
            "quiet": False
        }
        
        if args_dict.get('config') and os.path.exists(args_dict['config']):
            try:
                with open(args_dict['config'], 'r') as f:
                    file_config = json.load(f)
                    self.config.update(file_config)
            except json.JSONDecodeError as e:
                logging.error(f"Error parsing config file: {e}")
                sys.exit(1)
            except Exception as e:
                logging.error(f"Error reading config file: {e}")
                sys.exit(1)
                
        # Override with CLI arguments (if provided)
        cli_args = {k: v for k, v in args_dict.items() if v is not None}
        self.config.update(cli_args)

        self._validate_and_parse()

    def _validate_and_parse(self):
        # Validate URL
        if not self.config['url']:
            logging.error("No target URL provided.")
            sys.exit(1)
        
        parsed_url = urlparse(self.config['url'])
        if parsed_url.scheme not in ('http', 'https') or not parsed_url.netloc:
            logging.error(f"Invalid URL provided: {self.config['url']}")
            sys.exit(1)

        # Ensure lists are properly typed if passed as strings from CLI
        if isinstance(self.config['status'], str):
            try:
                self.config['status'] = [int(s.strip()) for s in self.config['status'].split(',')]
            except ValueError:
                logging.error("Status codes must be integers.")
                sys.exit(1)
        if isinstance(self.config['keywords'], str):
            self.config['keywords'] = [k.strip() for k in self.config['keywords'].split(',')]
        if isinstance(self.config['exts'], str):
            self.config['exts'] = [e.strip() for e in self.config['exts'].split(',')]
            
        # Validate output path
        self.config['output'] = os.path.abspath(self.config['output'])

class Crawler:
    def __init__(self, config):
        self.config = config.config
        self.visited = set()
        self.results = []
        self.semaphore = asyncio.Semaphore(self.config.get('threads', 10))

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
                                if self.config['json']:
                                    sys.stdout.write(json.dumps({"url": url, "status": status}) + "\n")
                                    sys.stdout.flush()
                                else:
                                    if not self.config['quiet']:
                                        sys.stdout.write(f"[+] [{status}] Found: {url}\n")
                                        sys.stdout.flush()
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

            except aiohttp.ClientError as e:
                logging.debug(f"Network error for {url}: {e}")
                return []
            except asyncio.TimeoutError:
                logging.debug(f"Timeout for {url}")
                return []
            except Exception as e:
                logging.debug(f"Unexpected error for {url}: {e}")
                return []

    async def crawl(self):
        logging.info(f"Starting EvilSpider on {self.config['url']}")
        logging.info(f"Threads: {self.config['threads']} | Exts: {self.config['exts']} | Status: {self.config['status']}")
        
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
                
                if len(self.visited) >= self.config['max_links']: # Safety threshold
                    logging.warning("Max limits reached.")
                    break

    def save_output(self):
        if self.results:
            try:
                with open(self.config['output'], 'w') as f:
                    json.dump(self.results, f, indent=4)
                logging.info(f"Saved {len(self.results)} targets to {self.config['output']}")
            except IOError as e:
                logging.error(f"Failed to save output to {self.config['output']}: {e}")

def parse_args():
    parser = argparse.ArgumentParser(
        description="EvilSpider - Fast Async Web Crawler",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Examples:
  Crawl a specific URL:
    %(prog)s crawl -u http://example.com

  Crawl with multiple extensions and specific status codes:
    %(prog)s crawl -u http://example.com -e php,bak,env -s 200,403

  Crawl quietly and output results in JSON format:
    %(prog)s crawl -u http://example.com --quiet --json
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    crawl_parser = subparsers.add_parser("crawl", help="Start the web crawler")
    crawl_parser.add_argument("-u", "--url", help="Target URL to crawl (e.g., http://example.com)")
    crawl_parser.add_argument("-c", "--config", help="Path to JSON config file (optional)")
    crawl_parser.add_argument("-t", "--threads", type=int, help="Number of concurrent threads/requests (default: 10)")
    crawl_parser.add_argument("-e", "--exts", help="Comma-separated extensions to hunt (e.g., php,bak,env,txt)")
    crawl_parser.add_argument("-s", "--status", help="Comma-separated HTTP status codes (e.g., 200,301,403) (default: 200)")
    crawl_parser.add_argument("-k", "--keywords", help="Comma-separated keywords to search in body")
    crawl_parser.add_argument("-p", "--params-only", action="store_true", help="Only flag URLs with parameters (?id=1)")
    crawl_parser.add_argument("-m", "--max-links", type=int, help="Maximum number of links to visit (default: 5000)")
    crawl_parser.add_argument("-o", "--output", help="Output file path (default: spider_results.json)")
    crawl_parser.add_argument("-j", "--json", action="store_true", help="Output results in JSON format to stdout")
    crawl_parser.add_argument("-q", "--quiet", action="store_true", help="Suppress informational output to stdout")
    crawl_parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    
    args = parser.parse_args()
    
    # If no arguments provided at all, show help
    if args.command is None:
        parser.print_help()
        sys.exit(0)

    return args

def setup_logging(verbose, quiet):
    level = logging.DEBUG if verbose else logging.INFO
    if quiet and not verbose:
        level = logging.WARNING

    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stderr)]
    )

def main():
    args = parse_args()
    args_dict = vars(args)

    setup_logging(args_dict.get('verbose', False), args_dict.get('quiet', False))

    config = EvilSpiderConfig(args_dict)
    spider = Crawler(config)

    try:
        asyncio.run(spider.crawl())
    except KeyboardInterrupt:
        logging.warning("User interrupted. Saving progress...")
        sys.exit(130)
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        sys.exit(1)
    finally:
        spider.save_output()

    sys.exit(0)

if __name__ == "__main__":
    main()
