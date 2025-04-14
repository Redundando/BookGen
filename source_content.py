from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from cacherator import JSONCache
from ghostscraper import GhostScraper
from logorator import Logger
from slugify import slugify
from smartllm import AsyncLLM
from toml_i18n import i18n

if TYPE_CHECKING:
    from book_generator import BookGenerator


class SourceContent(JSONCache):

    def __init__(self, bg: "BookGenerator", url=""):
        self.book_generator = bg
        self._text: str | None = None
        self._content_analysis: dict | None = None
        super().__init__(
                data_id=f"{slugify(self.book_generator.settings.title)}_{slugify(url)}",
                directory="data/sources",
                clear_cache=self.book_generator.clear_cache,
                ttl=self.book_generator.ttl)
        self.url = url
        self.scraper = GhostScraper(
            url=url,
            clear_cache=self.book_generator.clear_cache,
            ttl=self.book_generator.ttl,
            load_timeout=15000,
            max_retries=2)
        self.email_sharing = self.book_generator.settings.email
        self.title = self.book_generator.settings.title

    def __str__(self):
        return f"Source {self.url} ({self.title})"

    def __repr__(self):
        return self.__str__()

    async def _get_text_from_scrape(self):
        text = await self.scraper.text()
        self.scraper.json_cache_save()
        self.json_cache_save()
        return text

    async def text(self):
        if self._text is None:
            self._text = await self._get_text_from_scrape()
        return self._text

    async def text_length(self):
        return len(await self.text())

    @Logger(override_function_name="Generating Source Content Analysis")
    async def _get_content_analysis_from_llm(self):
        text = await self.text()
        with open(str(Path(__file__).parent / "i18n/source_content.understand_content.yaml"), "r") as f:
            json_schema = yaml.safe_load(f)
        prompt = i18n(
                "source_content.understand_content",
                title=self.book_generator.settings.title,
                author=self.book_generator.settings.author,
                further_information="",
                markdown=text,
                url=self.url)
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
        llm.json_cache_save()
        return llm.response

    async def content_analysis(self):
        if self._content_analysis is None:
            if await self.is_long_enough_for_analysis():
                self._content_analysis = await self._get_content_analysis_from_llm()
                self.json_cache_save()
            else:
                self._content_analysis = {}
        return self._content_analysis

    async def is_long_enough_for_analysis(self):
        return (await self.text_length()) >= self.book_generator.settings.min_source_length

    async def source_summary(self):
        result = []
        content_analysis = await self.content_analysis()
        for item in content_analysis.get("content_analysis", []):
            try:
                content_name = item.get("content_name", "No Name")
                coverage_rating = item.get("coverage_rating", "No Rating")
                analysis_notes = item.get("analysis_notes", "No Notes")
                result.append({"url": self.url, "content_name": content_name, "coverage_rating": coverage_rating, "analysis_notes": analysis_notes})
            except Exception as e:
                Logger.note(f"{e}")
        return result

    async def interesting_facts(self):
        result = []
        content_analysis = await self.content_analysis()
        for item in content_analysis.get("interesting_facts", []):
            try:
                fact = item.get("fact", "")
                result.append(fact)
            except Exception as e:
                Logger.note(f"{e}")
        return result

    async def run_analysis(self):
        if self._text is None:
            self._text = await self._get_text_from_scrape()
        if self._content_analysis is None and (await self.is_long_enough_for_analysis()) is True:
            self._content_analysis = await self._get_content_analysis_from_llm()
