from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from cacherator import Cached, JSONCache
from logorator import Logger
from slugify import slugify
from smartllm import AsyncLLM
from toml_i18n import i18n

from topic import Topic

if TYPE_CHECKING:
    from book_generator import BookGenerator


class TopicFinder(JSONCache):

    def __init__(self, bg: "BookGenerator") -> None:
        self.book_generator = bg
        self.sheet = self.book_generator.sheet
        data_id = f"{slugify(self.sheet.sheet_identifier)}"
        self._topic_information: list[dict] | None = None
        super().__init__(data_id=data_id, directory="data/topic_finder", ttl=self.book_generator.ttl, clear_cache=self.book_generator.clear_cache)
        self._source_summary = []
        self._topics: list[Topic] = []


    def __str__(self):
        return f"TopicFinder ({self.book_generator.settings.title})"

    def __repr__(self):
        return self.__str__()

    @property
    @Cached()
    def source_info_tab(self):
        return self.book_generator.source_finder.source_info_tab

    @property
    @Cached()
    def topic_information_tab(self):
        return self.book_generator.sheet.tab(tab_name="Topic Information", data_format="dict")

    def _load_source_summary_from_sheet(self):
        self._source_summary = self.source_info_tab.data

    def filtered_source_information(self, min_coverage_rating: int = 7, max_sources = 80):
        result = []
        for s in self._source_summary:
            if s.get("coverage_rating", 0) >= min_coverage_rating:
                result.append(s)
        result = sorted(result, key=lambda info: info["coverage_rating"], reverse=True)
        return result[:max_sources]

    @Logger()
    async def synthesize_sources(self):
        with open(str(Path(__file__).parent / "i18n/topic_finder.synthesize_sources.yaml"), "r") as f:
            json_schema = yaml.safe_load(f)
        prompt = i18n(
                "topic_finder.synthesize_sources",
                title=self.book_generator.settings.title,
                author=self.book_generator.settings.author,
                num_words=self.book_generator.settings.proposed_word_count,
                sources=self.filtered_source_information(min_coverage_rating=7))
        llm = AsyncLLM(
                base=self.book_generator.settings.complex_base,
                model=self.book_generator.settings.complex_model,
                api_key=self.book_generator.settings.complex_api_key,
                prompt=prompt,
                temperature=0.2,
                max_input_tokens=200_000,
                max_output_tokens=50_000,
                json_mode=True,
                json_schema=json_schema)
        await llm.execute()

        result = llm.response.get("topics", [])
        return result

    @Logger(override_function_name="Saving Topics to Google Doc")
    def save_topic_information_to_sheet(self):
        tab = self.topic_information_tab
        flatted_topic_information = []
        for row in self._topic_information:
            flat_row = row.copy()
            if flat_row.get("sources"):
                flat_row["sources"] = ", ".join([s.get("url") for s in flat_row["sources"]])
            flatted_topic_information.append(flat_row)
        tab.data = flatted_topic_information
        tab.write_data(overwrite_tab=True)

    async def run(self):
        self._load_source_summary_from_sheet()
        self._topic_information = await self.synthesize_sources()
        self.save_topic_information_to_sheet()
