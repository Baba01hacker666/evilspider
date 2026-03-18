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
