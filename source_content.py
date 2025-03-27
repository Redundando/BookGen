import json
from pathlib import Path
from typing import TYPE_CHECKING

from cacherator import Cached, JSONCache
from docorator import Docorator
from ghostscraper import GhostScraper
from logorator import Logger
from slugify import slugify
from smartllm import AsyncSmartLLM
from toml_i18n import i18n

if TYPE_CHECKING:
    from book_generator import BookGenerator


class SourceContent(JSONCache):

    def __init__(self, bg: "BookGenerator", url=""):
        self.book_generator = bg
        self.text: str | None = None
        self.content_analysis: dict | None = None
        super().__init__(data_id=f"{slugify(self.book_generator.settings.title)}_{slugify(url)}", directory="data/sources", clear_cache=self.book_generator.clear_cache, ttl=self.book_generator.ttl)
        self.url = url
        self.scraper = GhostScraper(url=url, clear_cache=self.book_generator.clear_cache, ttl=self.book_generator.ttl)
        self.email_sharing = self.book_generator.settings.email
        self.service_account_file = self.book_generator.settings.service_account_file
        self.title = self.book_generator.settings.title
        self._google_docs_initialized = False
        self.google_doc_source_text = Docorator(service_account_file=self.service_account_file, document_name=f"{slugify(self.title)}_{slugify(url)}",
                clear_cache=self.book_generator.clear_cache)
        self.google_doc_content_analysis = Docorator(service_account_file=self.service_account_file, document_name=f"Analysis {slugify(self.title)}_{slugify(url)}",
                clear_cache=self.book_generator.clear_cache)

    def __str__(self):
        return f"Source {self.url} ({self.title})"

    def __repr__(self):
        return self.__str__()

    async def initialize(self):
        if not self._google_docs_initialized:
            await self.google_doc_source_text.initialize()
            await self.google_doc_content_analysis.initialize()
            self._google_docs_initialized = True

    async def _get_text_from_scrape(self):
        return await self.scraper.text()

    async def _get_text_from_google_doc(self):
        return await self.google_doc_source_text.export_as_markdown()

    async def _save_text_to_google_doc(self):
        await self.google_doc_source_text.update_from_markdown(markdown_text=self.text)

    @Logger(override_function_name="Load Text")
    async def _get_text_from_doc_or_scrape(self):
        await self.initialize()
        self.text = await self._get_text_from_google_doc()
        if len(self.text) <= 10:
            self.text = await self._get_text_from_scrape()
            await self._save_text_to_google_doc()
        self.json_cache_save()
        return self.text

    async def get_text(self):
        if self.text is None:
            self.text = await self._get_text_from_doc_or_scrape()
        return self.text

    async def text_length(self):
        return len(await self.get_text())

    @property
    @Cached()
    def google_doc_markdown_url(self):
        return self.google_doc_source_text.url()

    @property
    @Cached()
    def google_doc_content_analysis_url(self):
        return self.google_doc_content_analysis.url()

    @Logger(override_function_name="Storing Content Analysis in Google Doc")
    async def _save_content_analysis_to_google_doc(self):
        markdown = ""
        for item in self.content_analysis.get("content_analysis", []):
            content_name = item.get("content_name", "No Name")
            coverage_rating = item.get("coverage_rating", "No Rating")
            analysis_notes = item.get("analysis_notes", "No Notes")
            markdown += f"## {content_name}\n\n"
            markdown += f"**Coverage Rating:** {coverage_rating}\n\n"
            markdown += f"{analysis_notes}\n\n"
        await self.google_doc_content_analysis.update_from_markdown(markdown_text=markdown)

    @Logger(override_function_name="Generating Source Content Analysis")
    async def _get_content_analysis_from_llm(self):
        text = await self.get_text()
        with open(str(Path(__file__).parent / "i18n/source_content.understand_content.json"), "r") as f:
            json_schema = json.load(f)
        prompt = i18n("source_content.understand_content", title=self.book_generator.settings.title, author=self.book_generator.settings.author, further_information="", markdown=text, url=self.url)
        llm = AsyncSmartLLM(base=self.book_generator.settings.general_base, model=self.book_generator.settings.general_model, api_key=self.book_generator.settings.general_api_key, prompt=prompt, temperature=0.2,
                max_input_tokens=200_000, max_output_tokens=15_000, stream=True, json_mode=True, json_schema=json_schema)
        await llm.execute()
        if llm.is_failed():
            Logger.note(f"LLM request failed: {llm.get_error()}")
            return []
        self.content_analysis = llm.response
        self.json_cache_save()
        await self._save_content_analysis_to_google_doc()
        return self.content_analysis



    async def _is_long_enough_for_analysis(self):
        return (await self.text_length()) >= self.book_generator.settings.min_source_length

    async def get_content_analysis(self):
        if self.content_analysis is None or self.content_analysis == []:
            if not (await self._is_long_enough_for_analysis()):
                return []
            self.content_analysis = await self._get_content_analysis_from_llm()
        return self.content_analysis

    @property
    @Cached()
    def source_summary(self):
        result = []
        if self.content_analysis is None or self.content_analysis == []:
            return []
        for item in self.content_analysis.get("content_analysis", []):
            try:
                content_name = item.get("content_name", "No Name")
                coverage_rating = item.get("coverage_rating", "No Rating")
                analysis_notes = item.get("analysis_notes", "No Notes")
                result.append({"url": self.url, "content_name": content_name, "coverage_rating": coverage_rating, "analysis_notes": analysis_notes})
            except Exception as e:
                print(item)
                Logger.note(f"{e}")
        return result

