from fastapi import FastAPI, Query
from pydantic import BaseModel
import httpx
from bs4 import BeautifulSoup
from typing import List, Optional
import urllib.parse

app = FastAPI(title="Manga Scraper API")

class SearchItem(BaseModel):
    provider: str            # ej: tmo-lector
    title: str
    url: str
    cover: Optional[str] = None

class Chapter(BaseModel):
    title: str
    url: str

class MangaMeta(BaseModel):
    provider: str
    title: str
    url: str
    cover: Optional[str] = None
    description: Optional[str] = None
    chapters: List[Chapter] = []

DUCK = "https://duckduckgo.com/html/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
}

def provider_from_url(u: str) -> str:
    if "tmo-lector.com" in u:
        return "tmo-lector"
    if "tumangaonline" in u:
        return "tumangaonline"
    return urllib.parse.urlparse(u).netloc

@app.get("/search", response_model=List[SearchItem])
async def search(q: str = Query(..., min_length=2), limit: int = 6):
    queries = [
        f"site:tmo-lector.com {q}",
        f"site:tumangaonline.site {q}",
    ]
    results: List[SearchItem] = []
    async with httpx.AsyncClient(headers=HEADERS, timeout=20) as client:
        for qq in queries:
            r = await client.get(DUCK, params={"q": qq})
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.select("a.result__a"):
                url = a.get("href")
                title = a.get_text(strip=True)
                if not url or not title:
                    continue
                # DuckDuckGo a veces envuelve la URL real
                if "/l/?" in url and "uddg=" in url:
                    url = urllib.parse.parse_qs(
                        urllib.parse.urlparse(url).query
                    ).get("uddg", [""])[0]
                results.append(SearchItem(
                    provider=provider_from_url(url),
                    title=title,
                    url=url
                ))
                if len(results) >= limit:
                    return results
    return results

@app.get("/manga", response_model=MangaMeta)
async def manga(url: str):
    async with httpx.AsyncClient(headers=HEADERS, timeout=20) as client:
        r = await client.get(url)
    soup = BeautifulSoup(r.text, "html.parser")

    title = soup.select_one('meta[property="og:title"]')
    desc  = soup.select_one('meta[property="og:description"]')
    img   = soup.select_one('meta[property="og:image"]')

    meta = MangaMeta(
        provider=provider_from_url(url),
        title=title.get("content") if title else (soup.title.get_text(strip=True) if soup.title else "Manga"),
        url=url,
        description=desc.get("content") if desc else None,
        cover=img.get("content") if img else None,
        chapters=[]
    )

    # Captura simple de capítulos (ajustable por sitio)
    for a in soup.select("a"):
        href = a.get("href") or ""
        text = a.get_text(" ", strip=True)
        if href.startswith("/") or href.startswith("#"):
            continue
        low = text.lower()
        if "cap" in low or "chapter" in low:
            meta.chapters.append(Chapter(title=text[:70], url=href))
        if len(meta.chapters) > 200:
            break

    return meta
