import requests
import logging
from bs4 import BeautifulSoup
from readability import Document
import html2text
import trafilatura
import hashlib
from typing import Tuple, Optional, Set

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Tags to remove - noise and clutter
NOISE_TAGS = [
    'script', 'style', 'nav', 'footer', 'aside', 
    'noscript', 'form', 'svg', 'iframe', 'header'
]

def fetch_url(url: str) -> str:
    """
    Fetch the HTML content from a URL with proper error handling.
    
    Args:
        url: The URL to fetch
        
    Returns:
        The HTML content as a string
        
    Raises:
        ValueError: If the URL is invalid or the content cannot be fetched
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        raise ValueError(f"Failed to fetch URL {url}: {str(e)}")

def clean_html(html_content: str) -> BeautifulSoup:
    """
    Clean HTML by removing noise tags.
    
    Args:
        html_content: HTML content as string
        
    Returns:
        BeautifulSoup object with cleaned HTML
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Remove noise tags
    for tag in NOISE_TAGS:
        for element in soup.find_all(tag):
            element.decompose()
            
    return soup

def extract_with_readability(html_content: str) -> Optional[str]:
    """
    Extract main content using readability-lxml.
    
    Args:
        html_content: Raw HTML content
        
    Returns:
        HTML string of the main content or None if extraction failed
    """
    try:
        doc = Document(html_content)
        title = doc.title()
        content = doc.summary()
        
        if not content or len(content) < 500:  # Arbitrary threshold
            return None
            
        # Add title as h1 if available
        if title:
            content = f"<h1>{title}</h1>\n{content}"
            
        return content
    except Exception as e:
        logger.warning(f"Readability extraction failed: {str(e)}")
        return None

def extract_with_trafilatura(html_content: str) -> Optional[str]:
    """
    Extract main content using trafilatura.
    
    Args:
        html_content: Raw HTML content
        
    Returns:
        HTML string of the main content or None if extraction failed
    """
    try:
        extracted_html = trafilatura.extract(
            html_content,
            output_format='html',
            include_links=True,
            include_images=True,
            include_formatting=True,
            include_tables=True
        )
        
        if not extracted_html or len(extracted_html) < 500:  # Arbitrary threshold
            return None
            
        return extracted_html
    except Exception as e:
        logger.warning(f"Trafilatura extraction failed: {str(e)}")
        return None

def extract_with_selector(soup: BeautifulSoup, selector: str) -> Optional[str]:
    """
    Extract content using a CSS selector.
    
    Args:
        soup: BeautifulSoup object
        selector: CSS selector to use
        
    Returns:
        HTML string of the selected content or None if not found
    """
    element = soup.select_one(selector)
    if not element:
        return None
        
    # Clean the element by removing noise tags
    for tag in NOISE_TAGS:
        for noise in element.find_all(tag):
            noise.decompose()
            
    # Check if there's enough content
    if len(element.get_text(strip=True)) < 200:  # Arbitrary threshold
        return None
        
    return str(element)

def convert_to_markdown(html_content: str) -> str:
    """
    Convert HTML to Markdown using html2text.
    
    Args:
        html_content: HTML content to convert
        
    Returns:
        Markdown string
    """
    converter = html2text.HTML2Text()
    converter.ignore_links = False
    converter.ignore_images = False
    converter.ignore_tables = False
    converter.body_width = 0  # Don't wrap lines
    converter.unicode_snob = True  # Preserve unicode
    converter.protect_links = True  # Don't escape links
    
    markdown = converter.handle(html_content)
    return markdown

def deduplicate_content(markdown: str, seen_content: Set[str]) -> Tuple[str, Set[str]]:
    """
    Simple deduplication to avoid repeated content.
    
    Args:
        markdown: The markdown content
        seen_content: Set of hashes of previously seen paragraphs
        
    Returns:
        Tuple of (deduplicated markdown, updated seen_content)
    """
    lines = markdown.split("\n")
    unique_lines = []
    
    for line in lines:
        line_hash = hashlib.md5(line.strip().encode()).hexdigest()
        
        # Skip if we've seen this exact content before
        # But only for substantive lines (>40 chars)
        if len(line.strip()) > 40 and line_hash in seen_content:
            continue
            
        unique_lines.append(line)
        
        # Only add substantive content to seen_content
        if len(line.strip()) > 40:
            seen_content.add(line_hash)
    
    return "\n".join(unique_lines), seen_content

def parse_url_to_markdown(url: str) -> str:
    """
    Main function to parse a URL to Markdown with fallback strategies.
    
    Args:
        url: URL to parse
        
    Returns:
        Markdown string of the extracted content
        
    Raises:
        ValueError: If the URL is invalid or no content could be extracted
    """
    try:
        html_content = fetch_url(url)
        soup = clean_html(html_content)
        extracted_html = None
        strategy_used = "unknown"
        seen_content = set()
        
        # Strategy 1: Try trafilatura first (modern and robust)
        extracted_html = extract_with_trafilatura(html_content)
        if extracted_html:
            logger.info(f"Used trafilatura extraction strategy for {url}")
            strategy_used = "trafilatura"
        
        # Strategy 2: Try readability
        if not extracted_html:
            extracted_html = extract_with_readability(html_content)
            if extracted_html:
                logger.info(f"Used readability extraction strategy for {url}")
                strategy_used = "readability"
        
        # Strategy 3: Try main tag
        if not extracted_html:
            extracted_html = extract_with_selector(soup, "main")
            if extracted_html:
                logger.info(f"Used main tag extraction strategy for {url}")
                strategy_used = "main"
        
        # Strategy 4: Try article tag
        if not extracted_html:
            extracted_html = extract_with_selector(soup, "article")
            if extracted_html:
                logger.info(f"Used article tag extraction strategy for {url}")
                strategy_used = "article"
        
        # Strategy 5: Try content tag or div with content ID
        if not extracted_html:
            for content_selector in ["#content", ".content", "[role='main']", ".main-content", "#main-content"]:
                extracted_html = extract_with_selector(soup, content_selector)
                if extracted_html:
                    logger.info(f"Used content selector {content_selector} for {url}")
                    strategy_used = f"selector:{content_selector}"
                    break
        
        # Final fallback: body tag (but more aggressive cleaning)
        if not extracted_html:
            body = soup.find('body')
            if body:
                # Remove more potential noise for body fallback
                for element in body.select('.sidebar, .comments, .related, .recommended, .ad, .advertisement'):
                    element.decompose()
                
                extracted_html = str(body)
                logger.info(f"Used body tag (fallback) extraction strategy for {url}")
                strategy_used = "body-fallback"
        
        # If we still don't have content, raise error
        if not extracted_html:
            raise ValueError(f"Could not extract content from {url} using any strategy")
        
        # Convert to Markdown
        markdown = convert_to_markdown(extracted_html)
        
        # Deduplicate content
        markdown, _ = deduplicate_content(markdown, seen_content)
        
        # Add metadata about extraction
        markdown = f"# {url}\n\n*Extracted using: {strategy_used}*\n\n{markdown}"
        
        # Write to file for testing
        with open("llms.md", "w", encoding="utf-8") as f:
            f.write(markdown)
        
        return markdown
        
    except Exception as e:
        logger.error(f"Error processing URL {url}: {str(e)}")
        raise ValueError(f"Failed to process URL: {str(e)}")

# For backwards compatibility with the existing API
def fetch_and_parse_url(url: str) -> str:
    """
    Backwards compatibility wrapper for the old function name.
    """
    return parse_url_to_markdown(url)