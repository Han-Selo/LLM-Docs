from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.responses import PlainTextResponse
from .parser import fetch_and_parse_url
from .crawler import crawl_and_parse_site

app = FastAPI()

class URLRequest(BaseModel):
    url: str

class CrawlRequest(BaseModel):
    url: str
    allow_subdomains: bool = False
    max_pages: int = 100
    respect_robots: bool = True

@app.post("/generate", response_class=PlainTextResponse)
async def generate_markdown(request: URLRequest):
    try:
        markdown_content = fetch_and_parse_url(request.url)
        with open("llms.md", "w") as file:
            file.write(markdown_content)
        return markdown_content
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="An error occurred while processing the request.")

@app.post("/crawl", response_class=PlainTextResponse)
async def crawl_site(request: CrawlRequest):
    try:
        markdown_content = crawl_and_parse_site(
            start_url=request.url,
            allow_subdomains=request.allow_subdomains,
            max_pages=request.max_pages,
            respect_robots=request.respect_robots
        )
        return markdown_content
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred while crawling the site: {str(e)}")