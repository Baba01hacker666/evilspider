import asyncio
import argparse
import sys
import logging
from config import EvilSpiderConfig
from crawler import Crawler

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

  Hidden endpoint hunt:
    %(prog)s crawl -u https://target.tld -s 200,403,404 --robots --sitemaps -d 4

  Upload surface hunt:
    %(prog)s crawl -u https://target.tld --detect-uploads -k upload,file,multipart -s 200,403

  Authenticated crawl with cookies:
    %(prog)s crawl -u https://target.tld -C 'session=abc123; role=admin' -H 'X-Requested-With: EvilSpider'

  Proxied Burp crawl:
    %(prog)s crawl -u https://target.tld -x http://127.0.0.1:8080 --follow-redirects --report-redirects

  403/200 recon mode:
    %(prog)s crawl -u https://target.tld -s 200,403 -e php,bak,env -p

  Browser-like Chrome fingerprint:
    %(prog)s crawl -u https://target.tld -f chrome
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
    crawl_parser.add_argument("-d", "--max-depth", type=int, help="Maximum crawl depth (default: 3)")
    crawl_parser.add_argument("--robots", action="store_true", help="Parse robots.txt")
    crawl_parser.add_argument("--sitemaps", action="store_true", help="Parse sitemap.xml")
    crawl_parser.add_argument("--detect-uploads", action="store_true", help="Detect forms with file uploads")
    crawl_parser.add_argument("-C", "--cookies", help="Cookies to use for requests (string or file path)")
    crawl_parser.add_argument("-T", "--timeout", type=int, help="Request timeout in seconds (default: 5)")
    crawl_parser.add_argument("--connect-timeout", type=int, help="Socket connect timeout in seconds (default: timeout)")
    crawl_parser.add_argument("--read-timeout", type=int, help="Socket read timeout in seconds (default: timeout)")
    crawl_parser.add_argument("-A", "--user-agent", help="Custom User-Agent string")
    crawl_parser.add_argument("-x", "--proxy", help="Proxy URL (e.g., http://127.0.0.1:8080)")
    crawl_parser.add_argument("-H", "--headers", action="append", help="Custom headers (e.g., -H 'X-Forwarded-For: 127.0.0.1')")
    crawl_parser.add_argument("--retries", type=int, help="Retries per request (default: 2)")
    crawl_parser.add_argument("--retry-backoff", type=float, help="Base exponential backoff in seconds (default: 0.5)")
    crawl_parser.add_argument("--retry-jitter", type=float, help="Max random jitter seconds added to backoff (default: 0.25)")
    crawl_parser.add_argument("--follow-redirects", action=argparse.BooleanOptionalAction, default=None, help="Follow HTTP redirects (default: true)")
    crawl_parser.add_argument("--report-redirects", action="store_true", help="Include redirect chain in output records")
    crawl_parser.add_argument("--max-body-bytes", type=int, help="Skip parsing bodies larger than this size in bytes (default: 1048576)")
    crawl_parser.add_argument("-f", "--fingerprint", choices=["chrome", "firefox", "safari", "edge"], help="Use browser-like User-Agent and request headers")
    
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


def print_logo(quiet):
    if quiet:
        return
    logo = r'''
      / _ \
    \_\(_)/_/
     _//o\\_
      /   \
    EvilSpider
    '''
    sys.stderr.write(logo + "\n")
    sys.stderr.flush()

def main():
    args = parse_args()
    args_dict = vars(args)

    setup_logging(args_dict.get('verbose', False), args_dict.get('quiet', False))
    print_logo(args_dict.get('quiet', False))

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
