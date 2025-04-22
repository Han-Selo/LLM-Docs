import os
import re
import time
import logging
import hashlib
import urllib.parse
import urllib.robotparser
from typing import Set, List, Dict, Tuple, Optional
from collections import deque

import requests
from bs4 import BeautifulSoup

from .parser import parse_url_to_markdown

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# File extensions to skip
SKIP_EXTENSIONS = {
    '.pdf', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx',
    '.zip', '.rar', '.tar', '.gz', '.7z',
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp',
    '.mp3', '.mp4', '.avi', '.mov', '.wmv', '.flv',
    '.exe', '.bin', '.iso', '.dmg', '.apk', '.ipa'
}

class WebsiteCrawler:
    """Crawler for extracting content from websites respecting robots.txt rules."""
    
    def __init__(self, start_url: str, allow_subdomains: bool = False, 
                 max_pages: int = 100, delay: float = 0.5,
                 respect_robots: bool = True):
        """
        Initialize the crawler with configuration parameters.
        
        Args:
            start_url: The URL to start crawling from
            allow_subdomains: Whether to follow links to subdomains
            max_pages: Maximum number of pages to crawl
            delay: Delay between requests in seconds
            respect_robots: Whether to respect robots.txt rules
        """
        self.start_url = start_url
        self.allow_subdomains = allow_subdomains
        self.max_pages = max_pages
        self.delay = delay
        self.respect_robots = respect_robots
        
        # Extract the base domain and scheme
        parsed = urllib.parse.urlparse(start_url)
        self.scheme = parsed.scheme
        self.netloc = parsed.netloc
        
        # If we start with www, we handle both www and non-www versions
        self.domain = self.netloc.replace('www.', '')
        
        # Track visited URLs, content hashes, and failed URLs
        self.visited_urls: Set[str] = set()
        self.content_hashes: Set[str] = set()
        self.failed_urls: Dict[str, str] = {}
        
        # Initialize robots.txt parser
        self.robots_parser = None
        if self.respect_robots:
            self._init_robots_parser()
            
    def _init_robots_parser(self) -> None:
        """Initialize the robots.txt parser."""
        try:
            robots_url = f"{self.scheme}://{self.netloc}/robots.txt"
            self.robots_parser = urllib.robotparser.RobotFileParser(robots_url)
            self.robots_parser.read()
            logger.info(f"Loaded robots.txt from {robots_url}")
        except Exception as e:
            logger.warning(f"Failed to load robots.txt: {e}")
            # Continue without robots.txt restrictions
            self.robots_parser = None
            
    def _normalize_url(self, url: str, parent_url: str) -> Optional[str]:
        """
        Normalize and validate a URL.
        
        Args:
            url: The URL to normalize
            parent_url: The URL where this link was found
            
        Returns:
            Normalized URL or None if the URL should be skipped
        """
        # Skip URLs that aren't http(s)
        if not url.startswith('http://') and not url.startswith('https://'):
            # Handle relative URLs
            if url.startswith('/'):
                # Absolute path relative to domain
                base_url = f"{self.scheme}://{self.netloc}"
                url = urllib.parse.urljoin(base_url, url)
            else:
                # Relative to current path
                url = urllib.parse.urljoin(parent_url, url)
        
        # Parse the URL
        parsed = urllib.parse.urlparse(url)
        
        # Skip non-HTTP(S) schemas
        if parsed.scheme not in ('http', 'https'):
            return None
            
        # Skip URLs outside our domain scope
        netloc = parsed.netloc.replace('www.', '')
        if self.allow_subdomains:
            # Check if it's a subdomain of our domain
            if not netloc.endswith(self.domain):
                return None
        else:
            # Strict domain check (no subdomains)
            if netloc != self.domain and netloc != f"www.{self.domain}":
                return None
        
        # Skip file extensions we don't want
        path = parsed.path.lower()
        if any(path.endswith(ext) for ext in SKIP_EXTENSIONS):
            return None
            
        # Remove fragments and query parameters
        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        
        # Ensure trailing slash consistency
        if not clean_url.endswith('/'):
            clean_url = f"{clean_url}/"
            
        return clean_url
        
    def _can_fetch(self, url: str) -> bool:
        """
        Check if the URL can be fetched according to robots.txt.
        
        Args:
            url: The URL to check
            
        Returns:
            True if the URL can be fetched, False otherwise
        """
        if not self.robots_parser:
            return True
            
        return self.robots_parser.can_fetch("*", url)
        
    def _extract_links(self, url: str, html_content: str) -> List[str]:
        """
        Extract links from HTML content.
        
        Args:
            url: The URL of the page
            html_content: The HTML content
            
        Returns:
            List of normalized URLs
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        links = []
        
        # Find all <a> tags with href attributes
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href'].strip()
            
            # Skip empty links and javascript actions
            if not href or href.startswith('javascript:') or href == '#':
                continue
                
            # Normalize the URL
            normalized_url = self._normalize_url(href, url)
            if normalized_url:
                links.append(normalized_url)
                
        return links
        
    def _is_duplicate_content(self, content: str) -> bool:
        """
        Check if content is duplicate based on its hash.
        
        Args:
            content: The content to check
            
        Returns:
            True if the content is duplicate, False otherwise
        """
        # Create a hash of the content
        content_hash = hashlib.md5(content.encode()).hexdigest()
        
        # Check if we've seen this hash before
        if content_hash in self.content_hashes:
            return True
            
        # Add the hash to our set
        self.content_hashes.add(content_hash)
        return False
        
    def crawl(self) -> str:
        """
        Crawl the website and extract content.
        
        Returns:
            Combined Markdown content from all crawled pages
        """
        # Queue for BFS crawling
        queue = deque([self.start_url])
        
        # Output file for the combined Markdown
        output_path = "llms.md"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(f"# Website Crawl: {self.start_url}\n\n")
            f.write(f"*Generated on {time.strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
            f.write(f"*Crawl configuration: max_pages={self.max_pages}, allow_subdomains={self.allow_subdomains}*\n\n")
            
        pages_crawled = 0
        all_markdown = ""
        
        # Start crawling
        logger.info(f"Starting crawl from {self.start_url}")
        logger.info(f"Configuration: max_pages={self.max_pages}, allow_subdomains={self.allow_subdomains}")
        
        while queue and pages_crawled < self.max_pages:
            # Get the next URL to crawl
            url = queue.popleft()
            
            # Skip if we've already visited this URL
            if url in self.visited_urls:
                continue
                
            # Add to visited set
            self.visited_urls.add(url)
            
            # Check robots.txt
            if not self._can_fetch(url):
                logger.info(f"Skipping {url} (blocked by robots.txt)")
                self.failed_urls[url] = "Blocked by robots.txt"
                continue
                
            try:
                logger.info(f"Crawling {url} ({pages_crawled + 1}/{self.max_pages})")
                
                # Fetch page content
                try:
                    # Extract Markdown using existing parser
                    page_markdown = parse_url_to_markdown(url)
                    pages_crawled += 1
                    
                    # Check for duplicate content
                    if self._is_duplicate_content(page_markdown):
                        logger.info(f"Skipping {url} (duplicate content)")
                        continue
                        
                    # Get the relative path for the header
                    parsed = urllib.parse.urlparse(url)
                    relative_path = parsed.path if parsed.path else "/"
                    
                    # Add page header and content to the combined Markdown
                    page_header = f"\n\n## Page: {relative_path}\n\n"
                    
                    # Append to file
                    with open(output_path, 'a', encoding='utf-8') as f:
                        f.write(page_header)
                        f.write(page_markdown)
                        f.write("\n\n---\n\n")
                    
                    all_markdown += page_header + page_markdown + "\n\n---\n\n"
                    
                    # Fetch HTML again to extract links
                    response = requests.get(url, timeout=15)
                    html_content = response.text
                    
                    # Extract links and add to queue
                    links = self._extract_links(url, html_content)
                    for link in links:
                        if link not in self.visited_urls:
                            queue.append(link)
                            
                except Exception as e:
                    logger.error(f"Failed to process {url}: {e}")
                    self.failed_urls[url] = str(e)
                
                # Delay between requests to be nice to the server
                time.sleep(self.delay)
                
            except Exception as e:
                logger.error(f"Error crawling {url}: {e}")
                self.failed_urls[url] = str(e)
                
        # Add summary to the end
        summary = f"\n\n## Crawl Summary\n\n"
        summary += f"* Total pages crawled: {pages_crawled}\n"
        summary += f"* Total pages visited: {len(self.visited_urls)}\n"
        summary += f"* Failed pages: {len(self.failed_urls)}\n"
        
        if self.failed_urls:
            summary += "\n### Failed URLs\n\n"
            for url, error in self.failed_urls.items():
                summary += f"* {url}: {error}\n"
                
        # Append summary to file
        with open(output_path, 'a', encoding='utf-8') as f:
            f.write(summary)
            
        all_markdown += summary
        
        logger.info(f"Crawl completed. Processed {pages_crawled} pages.")
        logger.info(f"Results saved to {output_path}")
        
        return all_markdown

def crawl_and_parse_site(
    start_url: str, 
    allow_subdomains: bool = False, 
    max_pages: int = 100, 
    delay: float = 0.5,
    respect_robots: bool = True
) -> str:
    """
    Crawl a website from a starting URL and extract content from all pages.
    
    Args:
        start_url: The URL to start crawling from
        allow_subdomains: Whether to follow links to subdomains
        max_pages: Maximum number of pages to crawl
        delay: Delay between requests in seconds
        respect_robots: Whether to respect robots.txt rules
        
    Returns:
        Combined Markdown content from all crawled pages
    """
    crawler = WebsiteCrawler(
        start_url=start_url,
        allow_subdomains=allow_subdomains,
        max_pages=max_pages,
        delay=delay,
        respect_robots=respect_robots
    )
    
    return crawler.crawl()