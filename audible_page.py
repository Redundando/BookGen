import json
import re
from html import unescape
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from bs4 import BeautifulSoup
from cacherator import JSONCache
from ghostscraper import GhostScraper
from logorator import Logger
from slugify import slugify
from smartllm import AsyncLLM
from toml_i18n import i18n, i18n_number, TomlI18n

if TYPE_CHECKING:
    from book_generator import BookGenerator


class AudiblePage(JSONCache):

    def __init__(self, bg: "None|BookGenerator", url="", clear_cache: bool = False, ttl: bool = 7):
        self.book_generator = bg
        data_id = f"{slugify(url)}"
        if self.book_generator:
            data_id = f"{slugify(self.book_generator.settings.title)}_{slugify(url)}"
            clear_cache = self.book_generator.clear_cache
            ttl = self.book_generator.ttl
        super().__init__(
                data_id=data_id, directory="data/audible_pages", clear_cache=clear_cache, ttl=ttl)
        self._is_correct_page_for_book = None
        self.url = url
        self.scraper = GhostScraper(
                url=self.url_with_country_override(), clear_cache=clear_cache, ttl=ttl, load_timeout=15000, max_retries=4)
        self._soup: None | BeautifulSoup = None

    def __str__(self):
        return f"Source {self.url}"

    def __repr__(self):
        return self.__str__()

    def url_with_country_override(self):
        params = "overrideBaseCountry=true&ipRedirectOverride=true"
        result = re.sub(r'(\?.*)?$', lambda m: ('&' if m.group(1) else '?') + params, self.url)
        return result

    async def _get_soup_from_scrape(self):
        html = await self.scraper.html()
        self.scraper.json_cache_save()
        self._soup = BeautifulSoup(html, "html.parser")
        return self._soup

    async def soup(self):
        if self._soup is None:
            self._soup = await self._get_soup_from_scrape()
        return self._soup

    async def run_analysis(self):
        if self._soup is None:
            self._soup = await self._get_soup_from_scrape()
        if self._is_correct_page_for_book is None:
            self._is_correct_page_for_book = (await self.analyse()).get("is_correct_product", False)

    async def asin(self):
        return re.search(r'/([A-Z0-9]{10})(?:[/?]|$)', self.url).group(1)

    async def ld_json(self):
        soup = await self.soup()
        result = [json.loads(d.string, strict=False) for d in
                soup.find_all(lambda tag: tag.name == 'script' and tag.get('type') in ['application/json', 'application/ld+json'])]
        flatten_list = lambda irregular_list: [element for item in irregular_list for element in flatten_list(item)] if type(
                irregular_list) is list else [irregular_list]
        return flatten_list(result)

    async def ld_json_type(self, type_=""):
        for data in await self.ld_json():
            if data.get("@type") and data["@type"] == type_:
                return data

    async def audiobook_ld_json(self):
        result = await self.ld_json_type(type_="PodcastSeries")
        if result: return result
        result = await self.ld_json_type(type_="Audiobook")
        if result: return result
        result = await self.ld_json_type(type_="BookSeries")
        if result: return result

    async def title(self):
        soup = await self.soup()
        h1 = soup.find("h1")
        if h1 is None:
            return None
        return h1.get_text()

    async def authors(self) -> []:
        json = await self.audiobook_ld_json()
        if json is None: return None
        author_list = json.get("author")
        result = [unescape(a["name"]) for a in author_list if "name" in a]
        return result

    async def author(self):
        return (await self.authors())[0]

    async def narrators(self) -> []:
        json = await self.audiobook_ld_json()
        if json is None: return []
        author_list = json.get("readBy")
        result = [unescape(a["name"]) for a in author_list if "name" in a]
        return result

    async def narrator(self):
        return (await self.narrators())[0]

    async def summary(self):
        soup = await self.soup()
        block = soup.find("adbl-text-block", {"slot": "summary"})
        if block is None:
            return None
        return block.get_text()

    async def duration(self) -> int:
        json = await self.audiobook_ld_json()
        if json is None: return 0
        result = 0
        dur = json.get("duration", "")
        hours = re.findall(r"(\d+)H", dur)
        if len(hours) > 0:
            result += int(hours[0]) * 60
        minutes = re.findall(r"(\d+)M", dur)
        if len(minutes) > 0:
            result += int(minutes[0])
        return result

    async def say_duration(self) -> str:
        (hours, minutes) = divmod(await self.duration(), 60)
        return f"""{"0" if hours < 10 else ""}{hours}:{"0" if minutes < 10 else ""}{minutes}"""

    async def language(self):
        json = await self.audiobook_ld_json()
        if json is None:
            return None
        return unescape(json.get("inLanguage"))

    async def is_abridged(self):
        json = await self.audiobook_ld_json()
        if json is None:
            return None
        return unescape(json.get("abridged", "false")) == "true"

    async def num_ratings(self):
        json = await self.audiobook_ld_json()
        if json is None:
            return 0
        if "aggregateRating" in json:
            rating = json["aggregateRating"]
            result = rating["ratingCount"]
            return int(result)
        return 0

    async def average_rating(self) -> float:
        json = await self.audiobook_ld_json()
        if json is None:
            return 0
        if await self.num_ratings() == 0:
            return 0
        if "aggregateRating" in json:
            rating = json["aggregateRating"]
            result = rating["ratingValue"]
            return float(result)
        return 0

    async def say_rating(self):
        if (await self.average_rating()) == 0:
            return "-"
        return f"{i18n_number(await self.average_rating(), decimals=1)} / 5"

    async def reviews(self):
        result = []
        soup = await self.soup()
        bc_tab_content = soup.find("div", {"class": "bc-tab-content"})
        if bc_tab_content is None: return []
        review_section = bc_tab_content.find("div", {"class": "bc-section"})
        if review_section is None:
            return None
        cards = review_section.find_all("div", {"class": "bc-row-responsive"}, recursive=False)
        for card in cards:
            if not card.find("h3"):
                continue
            review = {}
            heading = card.find("h3").text.replace("\n", "").strip()
            card_link = card.find("a", {"class": "bc-link bc-color-link bc-text-ellipses"})
            if card_link is None:
                continue
            review["name_of_reviewer"] = card_link.text
            # review["link_to_reviewer"] = i18n("url.audible") + card_link["href"]
            paragraphs = card.find("h3").parent.find_all("p")
            stop_words = i18n("general.review_stopwords").split(";")
            text = ""
            for p in paragraphs:
                con = False
                for stop_word in stop_words:
                    if stop_word in p.text: con = True
                if con: continue
                text += "<span>" + p.decode_contents().replace("\n", "").replace("\r", "").strip() + "</span>"
            review["text"] = f"""<p>\"<span>{heading}</span> {text}\"</p>"""
            try:
                review["likes"] = int(
                        card.select('p[class~="bc-size-footnote"]')[-1].text.replace("\n", "").strip().replace(
                                ",", "").replace(
                                " people found this helpful", "").replace(" person found this helpful", ""))
            except:
                review["likes"] = 0
            review["rating"] = int(card.select("span[class~='bc-pub-offscreen']")[0].text.replace("out of 5 stars", ""))

            if "Amazon Customer" in review["name_of_reviewer"]:
                continue

            result.append(review)
        return result

    async def image_url(self):
        json = await self.audiobook_ld_json()
        if json is None:
            return None
        return unescape(json.get("image", None))

    async def information(self):
        result = {
                "asin"       : await self.asin(),
                "title"      : await self.title(),
                "is_abridged": await self.is_abridged(),
                "authors"    : await self.authors(),
                "narrators"  : await self.narrators(),
                "summary"    : await self.summary(),
                "duration"   : await self.duration(),
                "rating"     : await self.average_rating(),
                "language"   : await self.language(),
                "reviews"    : await self.reviews()}
        return result

    @Logger()
    async def analyse(self):
        if await self.language() not in self.book_generator.settings.audiobook_languages: return {"is_correct_product": False}

        with open(str(Path(__file__).parent / "i18n/audible_page.analyse.yaml"), "r") as f:
            json_schema = yaml.safe_load(f)

        prompt = i18n(
                "audible_page.analyse",
                title=self.book_generator.settings.title,
                author=self.book_generator.settings.author,
                url=self.url,
                information=await self.information(),
                language=i18n("prompts.language"), )

        llm = AsyncLLM(
                base=self.book_generator.settings.general_base,
                model=self.book_generator.settings.general_model,
                api_key=self.book_generator.settings.general_api_key,
                prompt=prompt,
                temperature=0.2,
                max_input_tokens=200_000,
                max_output_tokens=50_000,
                json_mode=True,
                json_schema=json_schema)
        await llm.execute()

        result = llm.response
        return result

    async def is_correct_page_for_book(self):
        if self._is_correct_page_for_book is None:
            self._is_correct_page_for_book = (await self.analyse()).get("is_correct_product")
        return self._is_correct_page_for_book


async def main():
    import book_generator
    ap = AudiblePage(
            book_generator.BookGenerator(sheet_identifier="1UYxtgU_cHtcLE_Eh7lAZOfvu3hJ-Yqj3fPxQgXeGrws"),
            "https://www.audible.com/pd/1984-Audiobook/B09NMPS9HQ")
    await ap.run_analysis()
    print(await ap.is_correct_page_for_book())
    print(await ap.image_url())


if __name__ == "__main__":
    import asyncio

    TomlI18n.initialize(locale="en", fallback_locale="en", directory=str(Path(__file__).parent / "i18n"))
    asyncio.run(main())
