import json
from pathlib import Path
from typing import TYPE_CHECKING

from cacherator import Cached, JSONCache
from logorator import Logger
from slugify import slugify
from smartllm import AsyncSmartLLM
from toml_i18n import i18n

from helper import snake_case_keys, to_float, to_int
from topic import Topic

if TYPE_CHECKING:
    from book_generator import BookGenerator


class TopicFinder(JSONCache):

    def __init__(self, bg: "BookGenerator") -> None:
        self.book_generator = bg
        self.sheet = self.book_generator.sheet
        data_id = f"{slugify(self.sheet.sheet_identifier)}"
        super().__init__(data_id=data_id, directory="data/topic_finder", ttl=self.book_generator.ttl, clear_cache=self.book_generator.clear_cache)
        self.topic_information: list[dict] | None = None
        self._topics: list[Topic] = []
        self._article_structure = []

    def __str__(self):
        return f"TopicFinder ({self.book_generator.settings.title})"

    def __repr__(self):
        return self.__str__()

    @property
    @Cached()
    def topics_tab(self):
        return self.book_generator.sheet.tab(tab_name="Topics", data_format="dict", clear_cache=True)

    @property
    async def source_summary(self):
        return await self.book_generator.source_finder.source_summary

    @Logger()
    async def synthesize_sources(self):
        with open(str(Path(__file__).parent / "i18n/topic_finder.synthesize_sources.json"), "r") as f:
            json_schema = json.load(f)
        prompt = i18n(
                "topic_finder.synthesize_sources",
                title=self.book_generator.settings.title,
                author=self.book_generator.settings.author,
                further_information="",
                sources=await self.source_summary)
        llm = AsyncSmartLLM(
                base=self.book_generator.settings.general_base,
                model=self.book_generator.settings.general_model,
                api_key=self.book_generator.settings.general_api_key,
                prompt=prompt,
                temperature=0.2,
                max_input_tokens=200_000,
                max_output_tokens=25_000,
                stream=True,
                json_mode=True,
                json_schema=json_schema)
        await llm.execute()

        if llm.is_failed():
            error = llm.get_error()
            Logger.note(f"LLM request failed: {error}")
            return []
        self.topic_information = llm.response.get("topics", [])
        await self.save_topic_structure_to_google_doc()

    async def get_topic_information(self) -> list[dict]:
        if self.topic_information is None:
            await self._load_topics_from_google_doc()
        if self.topic_information is None or len(self.topic_information) == 0:
            await self.synthesize_sources()
        return self.topic_information

    async def get_article_structure(self):
        if self._article_structure is None or len(self._article_structure) == 0:
            topic_information = await self.get_topic_information()
            self._article_structure = []
            for topic in topic_information:
                self._article_structure.append(
                        {"order": topic["order"], "topic": topic["topic_name"], "details": topic["topic_notes"], "word_count": topic["word_count"]})
        return self._article_structure

    async def topics(self) -> list[Topic]:
        if self._topics is None or len(self._topics) == 0:
            self._topics = []
            topic_information = await self.get_topic_information()
            for topic in topic_information:
                try:
                    self._topics.append(Topic(bg=self.book_generator, topic_information=topic))
                except Exception as e:
                    Logger.note(f"{e}")
        return self._topics

    @Logger(override_function_name="Loading Topics from Google Doc")
    async def _load_topics_from_google_doc(self):
        tab_data = snake_case_keys(self.topics_tab.data)
        result = []
        for topic in tab_data:
            row = {}
            row["order"] = to_float(topic["order"], 999)
            row["topic_name"] = topic["topic"]
            row["topic_notes"] = topic["details"]
            row["word_count"] = to_int(topic["suggested_length"], 100)
            row["sources"] = [url.strip() for url in topic["sources"].split(",")]
            result.append(row)
        self.topic_information = result
        return result

    @Logger(override_function_name="Saving Topics to Google Doc")
    async def save_topic_structure_to_google_doc(self):
        tab = self.topics_tab
        tab.data = [["Order", "Topic", "Details", "Suggested Length", "Sources"]]
        topics = await self.get_topic_information()
        for topic in topics:
            row = []
            row.append(topic["order"])
            row.append(topic["topic_name"])
            row.append(topic["topic_notes"])
            row.append(topic["word_count"])
            sources = topic["sources"]
            urls = ", ".join([s.get("url",None) for s in sources])
            row.append(urls)
            tab.data.append(row)
        tab.write_data(overwrite_tab=True)
