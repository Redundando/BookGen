import asyncio
from typing import List, TYPE_CHECKING

from cacherator import Cached, JSONCache
from logorator import Logger
from slugify import slugify
from smartllm import SmartLLM
from toml_i18n import i18n

from _config import PERPLEXITY_API_KEY
from source_content import SourceContent

if TYPE_CHECKING:
    from book_generator import BookGenerator


class SourceFinder(JSONCache):
    MIN_LENGTH_TO_BE_VIABLE = 2000  # chars

    def __init__(self, bg: "BookGenerator") -> None:
        self.book_generator = bg
        self.sheet_identifier = self.book_generator.sheet_identifier
        data_id = f"{slugify(self.sheet_identifier)}"
        self._content = ""
        super().__init__(data_id=data_id, directory="data/source_finder", ttl=self.book_generator.ttl, clear_cache=self.book_generator.clear_cache)
        self._source_urls = []
        self.api_key = PERPLEXITY_API_KEY
        self._excluded_cache_vars = ["api_key"]

    def __str__(self):
        return f"SourceFinder ({self.book_generator.settings.title})"

    def __repr__(self):
        return self.__str__()

    @Cached()
    @Logger()
    def _find_source_urls(self) -> List[str]:
        prompt = i18n("source_finder.search", title=self.book_generator.settings.title, author=self.book_generator.settings.author)
        llm = SmartLLM(base=self.book_generator.settings.search_base, model=self.book_generator.settings.search_model, api_key=self.book_generator.settings.search_api_key, prompt=prompt, temperature=0.2,
                return_citations=True)
        llm.execute()

        if llm.is_failed():
            error = llm.get_error()
            Logger.note(f"LLM request failed: {error}")
            return []

        self._source_urls = llm.sources if hasattr(llm, "sources") else []
        Logger.note(f"Found information about '{self.book_generator.settings.title}' with {len(self._source_urls)} sources")
        self._save_source_urls()
        return self._source_urls

    @property
    @Cached()
    def sources_tab(self):
        return self.book_generator.sheet.tab(tab_name="Source URLs", data_format="list")

    @property
    @Cached()
    def source_info_tab(self):
        return self.book_generator.sheet.tab(tab_name="Source Information", data_format="list")

    @Logger()
    def _save_source_urls(self):
        tab = self.sources_tab
        tab.data = [["URL"]]
        for url in self._source_urls:
            tab.data.append([url])
        tab.write_data()

    @Logger()
    def _load_source_urls(self):
        tab = self.sources_tab
        self._source_urls = []
        for row in tab.data[1:]:
            self._source_urls.append(row[0])
        return self._source_urls

    @property
    def source_urls(self):
        if len(self._source_urls) == 0:
            self._load_source_urls()
        if len(self._source_urls) == 0:
            self._find_source_urls()
        return self._source_urls

    @property
    @Cached()
    def source_contents(self) -> list[SourceContent]:
        result = []
        for url in self.source_urls:
            sc = SourceContent(url=url, bg=self.book_generator)
            result.append(sc)
        return result

    async def _initialize_source_content_docs(self):
        tasks = []
        for sc in self.source_contents:
            tasks.append(sc.initialize())
        await asyncio.gather(*tasks)

    async def scrape_all_sources(self):
        tasks = []
        for sc in self.source_contents:
            tasks.append(sc.get_text())
        await asyncio.gather(*tasks)

    async def analyse_all_sources(self):
        tasks = []
        for sc in self.source_contents:
            tasks.append(sc.get_content_analysis())
        await asyncio.gather(*tasks)

    async def save_source_information_urls(self):
        tab = self.source_info_tab
        tab.data = [["URL", "URL Text Doc", "Text Length", "Content Information Doc"]]
        await self._initialize_source_content_docs()
        for sc in self.source_contents:
            tab.data.append([sc.url, sc.google_doc_markdown_url, await sc.text_length(), sc.google_doc_content_analysis_url])
        tab.write_data(overwrite_tab=True)

    @property
    @Cached()
    async def source_summary(self):
        result = []
        for sc in self.source_contents:
            if (await sc._is_long_enough_for_analysis()):
                result += sc.source_summary
        return result
