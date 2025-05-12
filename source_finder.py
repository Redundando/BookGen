import asyncio
from pathlib import Path
from trace import Trace
from typing import List, TYPE_CHECKING

import yaml
from cacherator import Cached, JSONCache
from logorator import Logger
from searcherator import Searcherator
from slugify import slugify
from smartllm import AsyncLLM
from toml_i18n import i18n

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
        self._source_urls: list[str] = []
        self._sources: list[SourceContent] = []
        self._refined_queries: list[str] = []
        self._excluded_cache_vars = ["api_key"]

    def __str__(self):
        return f"SourceFinder ({self.book_generator.settings.title})"

    def __repr__(self):
        return self.__str__()

    @property
    @Cached()
    def sources_tab(self):
        return self.book_generator.sheet.tab(tab_name="Source URLs", data_format="list")

    @property
    @Cached()
    def source_info_tab(self):
        return self.book_generator.sheet.tab(tab_name="Source Information", data_format="dict")

    @property
    @Cached()
    def refined_queries_tab(self):
        return self.book_generator.sheet.tab(tab_name="Refined Queries", data_format="list")

    @Logger()
    def _load_source_urls_from_sheet(self):
        tab = self.sources_tab
        self._source_urls = []
        for row in tab.data[1:]:
            self._source_urls.append(row[0])
        return self._source_urls

    @Logger()
    def _save_source_urls_to_sheet(self):
        tab = self.sources_tab
        tab.data = [["URL"]]
        for url in self._source_urls:
            tab.data.append([url])
        tab.write_data(overwrite_tab=True)

    @Logger()
    def _load_refined_queries_from_sheet(self):
        tab = self.refined_queries_tab
        self._refined_queries = []
        for row in tab.data[1:]:
            self._refined_queries.append(row[0])
        return self._refined_queries

    @Logger()
    def _save_refined_queries_to_sheet(self):
        tab = self.refined_queries_tab
        tab.data = [["Refined Queries"]]
        for query in self._refined_queries:
            tab.data.append([query])
        tab.write_data(overwrite_tab=True)

    @Logger()
    async def _find_source_urls(self, prompt: str | None = None) -> List[str]:
        if prompt is None:
            prompt = i18n("source_finder.search", title=self.book_generator.settings.title, author=self.book_generator.settings.author)
        search = Searcherator(
            prompt,
            num_results=self.book_generator.settings.urls_per_search,
            language=self.book_generator.settings.language,
            country=self.book_generator.settings.country,
            api_key=self.book_generator.settings.DEFAULT_BRAVE_API_KEY,
        )
        result = await search.urls()
        Logger.note(f"Found information '{prompt}' with {len(result)} sources")
        return result

    @property
    def source_urls(self):
        return self._source_urls

    @property
    @Cached(clear_cache=True)
    def source_contents(self) -> list[SourceContent]:
        result = []
        if len(self.source_urls) == 0:
            self._source_urls = self._load_source_urls_from_sheet()
        for url in self.source_urls:
            sc = SourceContent(url=url, bg=self.book_generator)
            result.append(sc)
        return result

    async def source_summary(self):
        result = []
        for sc in self._sources:
            if await sc.is_long_enough_for_analysis():
                result += await sc.source_summary()
        return result

    @Logger()
    async def _save_source_summary_to_sheet(self):
        tab = self.source_info_tab
        tab.data = await self.source_summary()
        tab.data.sort(key=lambda x: x.get("coverage_rating"), reverse=True)
        tab.write_data(overwrite_tab=True)

    @Logger()
    async def find_more_search_queries_for_topic(self):
        prompt = i18n(
                "source_finder.find_more_search_queries",
                title=self.book_generator.settings.title,
                author=self.book_generator.settings.author,
                num_queries=self.book_generator.settings.num_search_refinements,
                article_type=i18n(self.book_generator.settings.article_type_key),
                sources=(await self.source_summary()))
        with open(str(Path(__file__).parent / "i18n/source_finder.find_more_search_queries.yaml"), "r") as f:
            schema = yaml.safe_load(f)

        llm = AsyncLLM(
                base=self.book_generator.settings.general_base,
                model=self.book_generator.settings.general_model,
                api_key=self.book_generator.settings.general_api_key,
                prompt=prompt,
                temperature=0.2,
                max_input_tokens=200_000,
                max_output_tokens=50_000,
                json_schema=schema)

        result = await llm.execute()
        queries = [q.get("query") for q in result.get("queries")]
        return queries

    @Logger()
    async def _build_source_objects_from_urls(self):
        used_urls = [s.url for s in self._sources]
        for url in self._source_urls:
            if url in used_urls:
                continue
            self._sources.append(SourceContent(url=url, bg=self.book_generator))
            used_urls.append(url)

    @Logger()
    async def _analyse_all_sources(self):
        semaphore = asyncio.Semaphore(40)

        async def sem_task(source):
            async with semaphore:
                return await source.run_analysis()

        tasks = [sem_task(s) for s in self._sources]
        await asyncio.gather(*tasks)

    async def run(self):
        self._source_urls = []
        if not self.book_generator.clear_cache:
            self._source_urls = self._load_source_urls_from_sheet()
        if len(self._source_urls) == 0:
            self._source_urls = await self._find_source_urls()
            self._save_source_urls_to_sheet()

        self._sources = []
        await self._build_source_objects_from_urls()
        await self._analyse_all_sources()

        if not self.book_generator.clear_cache:
            self._refined_queries = self._load_refined_queries_from_sheet()
        if len(self._refined_queries) < self.book_generator.settings.num_search_refinements:
            self._refined_queries = list(dict.fromkeys(self._refined_queries + await self.find_more_search_queries_for_topic()))
            self._save_refined_queries_to_sheet()

        for query in self._refined_queries:
            refined_urls = await self._find_source_urls(query)
            self._source_urls = list(dict.fromkeys(self._source_urls + refined_urls))
        self._save_source_urls_to_sheet()

        await self._build_source_objects_from_urls()
        await self._analyse_all_sources()
        await self._save_source_summary_to_sheet()
