import requests
import argparse

def test_generate_endpoint(url="https://example.com"):
    """Test the /generate endpoint for single URL parsing"""
    endpoint = "http://0.0.0.0:8000/generate"
    payload = {"url": url}
    headers = {"Content-Type": "application/json"}
    
    print(f"\nTesting /generate endpoint with URL: {url}")
    
    try:
        response = requests.post(endpoint, json=payload, headers=headers)
        
        if response.status_code == 200:
            print(f"Success! Markdown content length: {len(response.text)} characters")
            print("First 300 characters of content:")
            print(response.text[:300] + "...\n")
            print(f"Full content saved to llms.md")
        else:
            print(f"Error: {response.status_code}")
            print(response.json())
    except Exception as e:
        print(f"Request failed: {e}")

def test_crawl_endpoint(url="https://example.com", max_pages=3):
    """Test the /crawl endpoint for website crawling"""
    endpoint = "http://0.0.0.0:8000/crawl"
    payload = {
        "url": url,
        "allow_subdomains": False,
        "max_pages": max_pages,
        "respect_robots": True
    }
    headers = {"Content-Type": "application/json"}
    
    print(f"\nTesting /crawl endpoint with URL: {url} (max_pages: {max_pages})")
    print("This may take some time depending on website size and max_pages...")
    
    try:
        response = requests.post(endpoint, json=payload, headers=headers)
        
        if response.status_code == 200:
            print(f"Success! Crawl complete.")
            print(f"Total markdown content length: {len(response.text)} characters")
            print("First 300 characters of content:")
            print(response.text[:300] + "...\n")
            print(f"Full content saved to llms.md")
        else:
            print(f"Error: {response.status_code}")
            print(response.json())
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Test the LLM-Docs API endpoints')
    parser.add_argument('--endpoint', '-e', choices=['generate', 'crawl', 'both'], default='both',
                       help='Which endpoint to test: generate, crawl, or both')
    parser.add_argument('--url', '-u', default='https://example.com',
                       help='URL to test with')
    parser.add_argument('--max-pages', '-p', type=int, default=3,
                       help='Maximum pages to crawl (only for crawl endpoint)')
    
    args = parser.parse_args()
    
    if args.endpoint in ['generate', 'both']:
        test_generate_endpoint(args.url)
        
    if args.endpoint in ['crawl', 'both']:
        test_crawl_endpoint(args.url, args.max_pages)