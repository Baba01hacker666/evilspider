import json
import os
import sys
import logging
from urllib.parse import urlparse


BROWSER_IMPERSONATION_PROFILES = {
    "chrome": {
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "headers": {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-CH-UA": '"Chromium";v="124", "Google Chrome";v="124", "Not(A:Brand";v="99"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        },
    },
    "firefox": {
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
        "headers": {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        },
    },
    "edge": {
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
        "headers": {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-CH-UA": '"Chromium";v="124", "Microsoft Edge";v="124", "Not(A:Brand";v="99"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        },
    },
    "safari": {
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
        "headers": {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        },
    },
    "chrome-android": {
        "user_agent": "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
        "headers": {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-CH-UA": '"Chromium";v="124", "Google Chrome";v="124", "Not(A:Brand";v="99"',
            "Sec-CH-UA-Mobile": "?1",
            "Sec-CH-UA-Platform": '"Android"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        },
    },
    "safari-ios": {
        "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
        "headers": {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        },
    },
}

class EvilSpiderConfig:
    def __init__(self, args_dict):
        self.config = {
            "url": None,
            "threads": 10,
            "timeout": 5,
            "connect_timeout": None,
            "read_timeout": None,
            "params_only": False,
            "status": [200],
            "keywords": [],
            "exts": [],
            "user_agent": os.environ.get("EVILSPIDER_USER_AGENT", "EvilSpider/2.0 (Customizable Crawler)"),
            "max_links": 5000,
            "output": "spider_results.json",
            "json": False,
            "quiet": False,
            "max_depth": 3,
            "robots": False,
            "sitemaps": False,
            "detect_uploads": False,
            "cookies": None,
            "parsed_cookies": None,
            "proxy": None,
            "headers": None,
            "parsed_headers": {},
            "impersonate": None,
            "retries": 2,
            "retry_backoff": 0.5,
            "retry_jitter": 0.25,
            "follow_redirects": True,
            "report_redirects": False,
            "max_body_bytes": 1048576
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
        self.cli_args = {k: v for k, v in args_dict.items() if v is not None}
        self.config.update(self.cli_args)

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

        for int_key in ("timeout", "connect_timeout", "read_timeout", "max_body_bytes", "retries"):
            value = self.config.get(int_key)
            if value is None:
                continue
            try:
                self.config[int_key] = int(value)
            except (TypeError, ValueError):
                logging.error(f"{int_key} must be an integer.")
                sys.exit(1)

        for float_key in ("retry_backoff", "retry_jitter"):
            try:
                self.config[float_key] = float(self.config[float_key])
            except (TypeError, ValueError):
                logging.error(f"{float_key} must be numeric.")
                sys.exit(1)

        if self.config.get("impersonate"):
            profile = BROWSER_IMPERSONATION_PROFILES.get(self.config["impersonate"])
            if not profile:
                logging.error(f"Unknown impersonation profile: {self.config['impersonate']}")
                sys.exit(1)

            if "user_agent" not in self.cli_args:
                self.config["user_agent"] = profile["user_agent"]
            self.config["parsed_headers"].update(profile["headers"])

        if self.config.get('cookies'):
            self.config['parsed_cookies'] = {}
            cookie_input = self.config['cookies']
            # Check if it's a file
            if os.path.isfile(cookie_input):
                try:
                    with open(cookie_input, 'r') as f:
                        cookie_str = f.read().strip()
                except Exception as e:
                    logging.error(f"Error reading cookie file {cookie_input}: {e}")
                    sys.exit(1)
            else:
                cookie_str = cookie_input

            # Parse cookie string
            try:
                import http.cookies
                simple_cookie = http.cookies.SimpleCookie()
                simple_cookie.load(cookie_str)
                for key, morsel in simple_cookie.items():
                    self.config['parsed_cookies'][key] = morsel.value
            except Exception as e:
                logging.error(f"Error parsing cookies: {e}")
                sys.exit(1)

        if self.config.get('headers'):
            for header in self.config['headers']:
                if ':' in header:
                    key, value = header.split(':', 1)
                    self.config['parsed_headers'][key.strip()] = value.strip()
                else:
                    logging.warning(f"Invalid header format: {header}")

        # Validate output path
        self.config['output'] = os.path.abspath(self.config['output'])
