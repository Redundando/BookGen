from typing import TYPE_CHECKING

from docorator import Docorator
from logorator import Logger
from slugify import slugify
from smartllm import AsyncLLM
from toml_i18n import i18n

if TYPE_CHECKING:
    from book_generator import BookGenerator
    from source_content import SourceContent

from cacherator import JSONCache


class Topic(JSONCache):

    def __init__(self, bg: "BookGenerator", topic_information: dict | None = None):
        self.book_generator = bg
        if topic_information is None:
            topic_information = {}
        self._source_information: list = []

        JSONCache.__init__(
                self,
                data_id=f"{self.book_generator.settings.title} - {topic_information.get('order')} {topic_information.get('topic_name')}",
                directory="data/topic",
                ttl=self.book_generator.ttl,
                clear_cache=self.book_generator.clear_cache)
        self._draft: str = ""
        self._refined_text: str = ""
        self._sources = []

        self.information = topic_information
        self.name = self.information.get("topic_name", "")
        self.details = self.information.get("topic_notes", "")
        self.order = self.information.get("order", 0)
        self.suggested_length = self.information.get("word_count", 0)
        self.source_urls = [s.strip() for s in self.information.get("sources", "").split(",")]

        self.google_doc_topic_draft = Docorator(
                service_account_file=self.book_generator.settings.service_account_file,
                document_name=f"Topic {slugify(self.name)} ({slugify(self.book_generator.settings.title)})",
                clear_cache=self.book_generator.clear_cache)

        self.google_doc_refined_topic_text = Docorator(
                service_account_file=self.book_generator.settings.service_account_file,
                document_name=f"Refined Topic {slugify(self.name)} ({slugify(self.book_generator.settings.title)})",
                clear_cache=self.book_generator.clear_cache)

        self._google_docs_initialized = False

    def __str__(self):
        return f"Topic {self.name}"

    def __repr__(self):
        return self.__str__()

    async def initialize(self):
        if not self._google_docs_initialized:
            Logger.note(f"Initializing Google Docs for Topic {self.name}")
            await self.google_doc_topic_draft.initialize()
            await self.google_doc_refined_topic_text.initialize()
            if not self.book_generator.clear_cache:
                await self._get_draft_from_google_doc()
                await self._get_refined_text_from_google_doc()
            self._google_docs_initialized = True

    @property
    def sources(self) -> list["SourceContent"]:
        if len(self._sources) == 0:
            self._sources = []
            for s in self.book_generator.sources:
                source_urls = self.source_urls
                if s.url in source_urls:
                    self._sources.append(s)
        return self._sources

    async def source_information(self):
        if len(self._source_information) == 0:
            self._source_information = []
            for source in self.sources:
                row = {"url": source.url, "text": await source.text()}
                self._source_information.append(row)
        return self._source_information

    @Logger(override_function_name="Loading Draft from Google Doc")
    async def _get_draft_from_google_doc(self):
        self._draft = await self.google_doc_topic_draft.export_as_markdown()
        return self._draft

    @Logger(override_function_name="Loading Refined Text from Google Doc")
    async def _get_refined_text_from_google_doc(self):
        self._refined_text = await self.google_doc_refined_topic_text.export_as_markdown()
        return self._refined_text

    async def draft(self):
        if len(self._draft) == 0:
            self._draft = await self._get_draft_from_google_doc()
        if len(self._draft) < 10:
            await self.write_draft_with_llm_and_save_to_google_doc()
        return self._draft

    async def refined_text(self):
        if len(self._refined_text) == 0:
            self._refined_text = await self._get_refined_text_from_google_doc()
        if len(self._refined_text) < 10:
            await self.refine_draft_with_llm_and_save_to_google_doc()
        return self._refined_text

    async def text_or_draft(self) -> str:
        if len(self._refined_text) > 10:
            return await self.refined_text()
        return await self.draft()

    async def draft_word_count(self) -> int:
        return len(self._draft.split())

    async def refined_text_word_count(self) -> int:
        return len(self._refined_text.split())

    async def _write_draft_with_llm(self):
        source_information = await self.source_information()
        article_structure = self.book_generator.article_writer.article_structure
        word_count = self.suggested_length
        prompt = i18n(
                "topic.write_draft",
                title=self.book_generator.settings.title,
                author=self.book_generator.settings.author,
                source_information=source_information,
                article_structure=article_structure,
                word_count=word_count,
                details=self.details,
                topic=self.name,
                language=i18n("style.language"), )
        llm = AsyncLLM(
                base=self.book_generator.settings.writing_base,
                model=self.book_generator.settings.writing_model,
                api_key=self.book_generator.settings.writing_api_key,
                prompt=prompt,
                temperature=0.2,
                max_input_tokens=200_000,
                max_output_tokens=50_000,
                stream=True)
        await llm.execute()
        self._draft = llm.response
        self.json_cache_save()
        return self._draft

    async def _refine_topic_with_llm(self):
        article = await self.book_generator.article_writer.full_article_draft()

        prompt = i18n(
                "topic.refine_text",
                title=self.book_generator.settings.title,
                author=self.book_generator.settings.author,
                section_number=self.order,
                article=article,
                topic=self.name)
        llm = AsyncLLM(
                base=self.book_generator.settings.writing_base,
                model=self.book_generator.settings.writing_model,
                api_key=self.book_generator.settings.writing_api_key,
                prompt=prompt,
                temperature=0.2,
                max_input_tokens=200_000,
                max_output_tokens=50_000,
                stream=True)
        await llm.execute()
        self._refined_text = llm.response
        self.json_cache_save()


        prompt_language = i18n(
                "topic.refine_language",
                title=self.book_generator.settings.title,
                author=self.book_generator.settings.author,
                topic=self.name,
                section=self._refined_text,
                language=i18n("style.language"))

        llm_language = AsyncLLM(
                base=self.book_generator.settings.writing_base,
                model=self.book_generator.settings.writing_model,
                api_key=self.book_generator.settings.writing_api_key,
                prompt=prompt_language,
                temperature=0.2,
                max_input_tokens=200_000,
                max_output_tokens=50_000,
                stream=True)
        await llm_language.execute()

        self._refined_text = llm_language.response
        self.json_cache_save()

        return self._refined_text

    async def write_draft_with_llm_and_save_to_google_doc(self):
        await self.initialize()
        await self._write_draft_with_llm()
        await self.google_doc_topic_draft.update_from_markdown(markdown_text=self._draft)

    async def refine_draft_with_llm_and_save_to_google_doc(self):
        await self.initialize()
        await self._refine_topic_with_llm()
        await self.google_doc_refined_topic_text.update_from_markdown(markdown_text=self._refined_text)
