import logging
import os
import asyncio
import aiohttp
from aiohttp import ClientSession
import aiofiles
import json
import re
import sys

# Configurations
DEFAULT_WORDLIST = 'Wordlist/pro_100.txt'
DEFAULT_OUTPUT = 'endpoints.txt'
DEFAULT_HEADERS = {}
DEFAULT_COOKIES = {}
VALID_STATUS_CODES = list(range(200, 300)) + [401, 403]
DEFAULT_METHODS = ['HEAD']
MAX_CONCURRENT_REQUESTS = 100  # Rate limiting
LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
COMMON_PATHS = ['/admin', '/login', '/dashboard', '/user', '/api']

# Setup logger
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger('FuzzDriller')

# Color ANSI escape codes
class Color:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    CYAN = '\033[96m'
    PURPLE = '\033[35m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


# Enhanced Bull's head ASCII Art + NasHLabs
BULLS_HEAD = r"""
          .     .
       .  |       |   .
        . |       |     .
         \ |     | / 
          \|     |/
       . 0 \     / 0  . 
      .      \_/       .  
          /  |N|  \         
         |   |A|   |        
     ----|   |S|   |-----    
       .  \__|H|__/   .  
     FuzzDriller(NasHLabx)
"""

class FuzzDriller:
    def __init__(self, base_url, wordlist, output_file, headers, cookies, methods, valid_status_codes):
        self.base_url = base_url.rstrip('/')
        self.wordlist = wordlist
        self.output_file = output_file
        self.headers = headers
        self.cookies = cookies
        self.methods = methods
        self.valid_status_codes = valid_status_codes
        self.found_endpoints = set()
        self.session = None
        self.total_tasks = 0
        self.completed_tasks = 0

    async def _fetch(self, path, method):
        """Perform an HTTP request."""
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            async with self.session.request(method, url, headers=self.headers, cookies=self.cookies) as response:
                if response.status in self.valid_status_codes:
                    logger.info(f"{Color.OKGREEN}[{response.status}] {url}{Color.ENDC}")
                    self.found_endpoints.add(url)
                return response.status
        except Exception as e:
            logger.error(f"{Color.FAIL}Error fetching {url}: {e}{Color.ENDC}")

        finally:
            # Increment completed task count and show progress
            self.completed_tasks += 1
            self._print_progress_bar()

    async def _process_paths(self, paths):
        """Process paths asynchronously."""
        sem = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)  # Rate limiting
        tasks = []

        async def _bound_fetch(path, method):
            async with sem:
                await self._fetch(path, method)

        self.total_tasks = len(paths) * len(self.methods)
        print(f"{Color.CYAN}Total tasks: {self.total_tasks}{Color.ENDC}")
        for path in paths:
            for method in self.methods:
                tasks.append(_bound_fetch(path, method))
        await asyncio.gather(*tasks)

    async def _load_wordlist(self):
        """Load paths from the wordlist."""
        paths = []
        if os.path.exists(self.wordlist):
            with open(self.wordlist, 'r') as file:
                paths.extend([line.strip() for line in file if line.strip()])
        # Auto-detect common paths if not in the wordlist
        paths.extend(COMMON_PATHS)
        return list(set(paths))  # Ensure unique paths

    async def start(self):
        """Start fuzzing."""
        paths = await self._load_wordlist()
        logger.info(f"Loaded {len(paths)} paths from the wordlist.")
        async with ClientSession() as session:
            self.session = session
            await self._process_paths(paths)
            self._save_results()

    def _save_results(self):
        """Save discovered endpoints to the output file."""
        if not self.found_endpoints:
            logger.warning(f"{Color.WARNING}No endpoints discovered.{Color.ENDC}")
            return
        with open(self.output_file, 'w') as file:
            for endpoint in sorted(self.found_endpoints):
                file.write(f"{endpoint}\n")
        logger.info(f"Results saved to '{self.output_file}'.")

    async def download_content(self, url):
        """Download and save the content of a discovered endpoint."""
        try:
            async with self.session.get(url, headers=self.headers, cookies=self.cookies) as response:
                if response.status in self.valid_status_codes:
                    content_type = response.headers.get('Content-Type', '')
                    extension = self._get_file_extension(content_type)
                    if extension:
                        file_name = self._sanitize_filename(url)
                        file_path = os.path.join('downloaded_pages', f"{file_name}.{extension}")
                        os.makedirs(os.path.dirname(file_path), exist_ok=True)
                        async with aiofiles.open(file_path, 'w', encoding='utf-8') as file:
                            await file.write(await response.text())
                        logger.info(f"{Color.OKGREEN}Downloaded: {url} -> {file_path}{Color.ENDC}")
        except Exception as e:
            logger.error(f"{Color.FAIL}Failed to download {url}: {e}{Color.ENDC}")

    def _get_file_extension(self, content_type):
        """Determine the file extension based on Content-Type."""
        if 'text/html' in content_type:
            return 'html'
        elif 'application/javascript' in content_type:
            return 'js'
        elif 'application/x-httpd-php' in content_type or 'text/x-php' in content_type:
            return 'php'
        return None

    def _sanitize_filename(self, url):
        """Sanitize URL to use as a file name."""
        return re.sub(r'[^\w\-_]', '_', url.replace(self.base_url, '').strip('/'))

    async def download_discovered_endpoints(self):
        """Download the content of all discovered endpoints."""
        logger.info(f"{Color.CYAN}Downloading content of discovered endpoints...{Color.ENDC}")
        tasks = [self.download_content(url) for url in self.found_endpoints]
        await asyncio.gather(*tasks)
        logger.info(f"{Color.OKGREEN}Download completed. Check the 'downloaded_pages' directory.{Color.ENDC}")

    def _print_progress_bar(self):
        """Print a simple progress bar."""
        progress = (self.completed_tasks / self.total_tasks) * 100
        bar = '=' * int(progress // 2)
        sys.stdout.write(f"\r[{bar:<50}] {progress:.2f}%")
        sys.stdout.flush()


def display_welcome_screen():
    """Display the welcome screen."""
    print(f"{Color.CYAN}=" * 50)
    print(f"{Color.PURPLE}{BULLS_HEAD}{Color.ENDC}")
    print(f"{Color.OKBLUE}Welcome to NasHLabx Async URL Fuzzer and Downloader {Color.ENDC}")
    print(f"{Color.OKGREEN}Unleash the Power of Technology for Discovering Hidden Endpoints{Color.ENDC}")
    print(f"{Color.CYAN}=" * 50)
    print(f"\n{Color.BOLD}Options:{Color.ENDC}")
    print(f"1. Start fuzzing")
    print(f"2. Set configurations (URL, wordlist, output file, etc.)")
    print(f"3. View current configurations")
    print(f"4. Download discovered directories")
    print(f"5. Exit")
    print(f"{Color.CYAN}=" * 50)


def interactive_menu():
    """Interactive menu for user input."""
    base_url = None
    wordlist = DEFAULT_WORDLIST
    output_file = DEFAULT_OUTPUT
    headers = DEFAULT_HEADERS
    cookies = DEFAULT_COOKIES
    methods = DEFAULT_METHODS
    valid_status_codes = VALID_STATUS_CODES

    while True:
        display_welcome_screen()
        choice = input(f"{Color.OKBLUE}Select an option: {Color.ENDC}").strip()

        if choice == '1':  # Start fuzzing
            if not base_url:
                print(f"{Color.FAIL}Please set the target URL in the configurations first.{Color.ENDC}")
                continue
            print(f"\n{Color.OKGREEN}Starting fuzzing...{Color.ENDC}")
            fuzzer = FuzzDriller(
                base_url=base_url,
                wordlist=wordlist,
                output_file=output_file,
                headers=headers,
                cookies=cookies,
                methods=methods,
                valid_status_codes=valid_status_codes
            )
            asyncio.run(fuzzer.start())

        elif choice == '2':  # Set configurations
            print(f"\n{Color.OKBLUE}Set Configurations:{Color.ENDC}")
            base_url = input(f"Enter target URL [{base_url or 'Not set'}]: ").strip() or base_url
            wordlist = input(f"Enter wordlist file path [{wordlist}]: ").strip() or wordlist
            output_file = input(f"Enter output file path [{output_file}]: ").strip() or output_file
            headers_input = input("Enter custom headers as JSON (leave blank for none): ").strip()
            if headers_input:
                headers = json.loads(headers_input)
            cookies_input = input("Enter custom cookies as JSON (leave blank for none): ").strip()
            if cookies_input:
                cookies = json.loads(cookies_input)
            methods_input = input(f"Enter HTTP methods as comma-separated values [{','.join(methods)}]: ").strip()
            if methods_input:
                methods = methods_input.split(',')
            status_codes_input = input(f"Enter valid status codes as comma-separated values [{','.join(map(str, valid_status_codes))}]: ").strip()
            if status_codes_input:
                valid_status_codes = list(map(int, status_codes_input.split(',')))
            print(f"{Color.OKGREEN}Configurations updated.{Color.ENDC}")

        elif choice == '3':  # View current configurations
            print(f"\n{Color.OKBLUE}Current Configurations:{Color.ENDC}")
            print(f"Target URL: {base_url or 'Not set'}")
            print(f"Wordlist File: {wordlist}")
            print(f"Output File: {output_file}")
            print(f"Headers: {json.dumps(headers, indent=2)}")
            print(f"Cookies: {json.dumps(cookies, indent=2)}")
            print(f"HTTP Methods: {', '.join(methods)}")
            print(f"Valid Status Codes: {', '.join(map(str, valid_status_codes))}")
            input(f"\n{Color.OKGREEN}Press Enter to return to the main menu...{Color.ENDC}")

        elif choice == '4':  # Download discovered directories
            if not base_url:
                print(f"{Color.FAIL}Please scan the target URL first.{Color.ENDC}")
                continue
            print(f"\n{Color.OKGREEN}Downloading discovered directories...{Color.ENDC}")
            fuzzer = FuzzDriller(
                base_url=base_url,
                wordlist=wordlist,
                output_file=output_file,
                headers=headers,
                cookies=cookies,
                methods=methods,
                valid_status_codes=valid_status_codes
            )
            asyncio.run(fuzzer.download_discovered_endpoints())

        elif choice == '5':  # Exit
            print(f"{Color.FAIL}Exiting the program. Goodbye!{Color.ENDC}")
            break

        else:
            print(f"{Color.FAIL}Invalid choice. Please try again.{Color.ENDC}\n")


if __name__ == '__main__':
    interactive_menu()
