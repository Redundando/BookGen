from urllib.parse import urlparse, urlunparse
import json
import re
from html import unescape
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from bs4 import BeautifulSoup
from cacherator import JSONCache
from ghostscraper import GhostScraper
from googlesearch import search
from logorator import Logger
from slugify import slugify
from smartllm import AsyncLLM
from toml_i18n import i18n, TomlI18n
from book_generator import BookGenerator

if TYPE_CHECKING:
    from book_generator import BookGenerator


class AudibleSearch(JSONCache):

    def __init__(self, bg: "BookGenerator"):
        self.book_generator = bg
        self.search_term = f"{self.book_generator.settings.title} {self.book_generator.settings.author}"
        self.search_parameter = slugify(self.search_term).replace("-", "+")
        url = f"""{i18n("url.audible")}/search?keywords={self.search_parameter}&k={self.search_parameter}&pageSize=50"""
        super().__init__(
                data_id=f"{slugify(self.book_generator.settings.title)}_{slugify(self.book_generator.settings.author)}",
                directory="data/audible_search",
                clear_cache=self.book_generator.clear_cache,
                ttl=self.book_generator.ttl)
        self.scraper = GhostScraper(
                url=url, clear_cache=self.book_generator.clear_cache, ttl=self.book_generator.ttl, load_timeout=15000, max_retries=5)
        self._soup: None | BeautifulSoup = None

    def __str__(self):
        return f"Audible Search ({self.search_term})"

    def __repr__(self):
        return self.__str__()

    async def _get_soup_from_scrape(self):
        html = await self.scraper.html()
        self.scraper.json_cache_save()
        self._soup = BeautifulSoup(html, "html.parser")
        return self._soup

    async def soup(self):
        if self._soup is None:
            self._soup = await self._get_soup_from_scrape()
        return self._soup

    async def product_links(self):
        soup = await self.soup()
        product_list_items = soup.find_all(class_="productListItem")
        link_items = []
        for product_list_item in product_list_items:
            link_items += product_list_item.find_all('a', href=re.compile(r'^/pd/'))
        links = [link.get("href") for link in link_items]
        stripped_links = [urlunparse(urlparse(link)._replace(query='', fragment='')) for link in links]
        proper_links = [f"{i18n('url.audible')}{link}" for link in list(set(stripped_links))]
        return proper_links

async def main():
    aus = AudibleSearch(BookGenerator(sheet_identifier="1tW-Pbbq6pJ908LFtRaahvtiV2DX7bzLm1_heSDDK7U8", clear_cache=False))
    print(await aus.product_links())


if __name__ == "__main__":
    import asyncio

    TomlI18n.initialize(locale="de", fallback_locale="en", directory=str(Path(__file__).parent / "i18n"))
    asyncio.run(main())