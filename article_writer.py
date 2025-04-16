import asyncio
from typing import TYPE_CHECKING

from cacherator import Cached, JSONCache
from docorator import Docorator
from logorator import Logger
from slugify import slugify
from toml_i18n import i18n

from topic import Topic

if TYPE_CHECKING:
    from book_generator import BookGenerator


def _sanitize_markdown(markdown: str = ""):
    return markdown.replace("```", "").replace("markdown", "")


class ArticleWriter(JSONCache):

    def __init__(self, bg: "BookGenerator") -> None:
        self.book_generator = bg
        self.sheet = self.book_generator.sheet
        data_id = f"{slugify(self.sheet.sheet_identifier)}"
        super().__init__(data_id=data_id, directory="data/article_writer", ttl=self.book_generator.ttl, clear_cache=self.book_generator.clear_cache)
        self._initialized = False
        self._topic_information = None
        self._full_article_draft = None
        self._sections = []

        self.google_doc_final_article = Docorator(
                service_account_file=self.book_generator.settings.service_account_file,
                document_name=f"Article {slugify(self.book_generator.settings.author)} {slugify(self.book_generator.settings.title)}",
                clear_cache=self.book_generator.clear_cache)

    @property
    def topics_tab(self):
        return self.book_generator.topic_finder.topic_information_tab

    def topic_information(self):
        if self._topic_information is None:
            self._topic_information = self.topics_tab.data
        return self._topic_information

    @property
    @Cached(clear_cache=True)
    def topics(self):
        topics = []
        for ti in self.topic_information():
            topics.append(Topic(bg=self.book_generator, topic_information=ti))
        return topics

    @property
    @Cached(clear_cache=True)
    def article_structure(self):
        result = []
        for topic in self.topics:
            row = {
                    "order"           : topic.order,
                    "topic_name"      : topic.name,
                    "topic_notes"     : topic.details,
                    "suggested_length": topic.suggested_length,
                    "sources"         : topic.source_urls}
            result.append(row)
        return result

    async def _initialize_topic_content_docs(self):
        if self._initialized:
            return
        tasks = []
        for topic in (self.topics):
            tasks.append(topic.initialize())
        await asyncio.gather(*tasks)
        self.initialized = True

    @Logger(override_function_name="Saving Topics to Google Doc")
    async def save_topic_structure_to_google_doc(self):
        tab = self.topics_tab
        tab.data = [
                ["order", "topic_name", "topic_notes", "word_count", "sources", "draft_url", "draft_word_count", "refined_url", "refined_word_count"]]
        for topic in self.topics:
            row = [topic.order, topic.name, topic.details, topic.suggested_length]
            urls = ", ".join([s.url for s in topic.sources])
            row.append(urls)
            row.append(topic.google_doc_topic_draft.url())
            row.append(await topic.draft_word_count())
            row.append(topic.google_doc_refined_topic_text.url())
            row.append(await topic.refined_text_word_count())
            tab.data.append(row)
        tab.write_data(overwrite_tab=True)

    @Logger()
    async def write_all_drafts(self):
        tasks = []
        for topic in self.topics:
            tasks.append(topic.write_draft_with_llm_and_save_to_google_doc())
        await asyncio.gather(*tasks)
        await self.save_topic_structure_to_google_doc()  # we call this again to update the tab with the correct draft word count

    async def full_article_draft(self):
        if self._full_article_draft is None:
            self._full_article_draft = []
            for topic in self.topics:
                row = {"order": topic.order, "topic": topic.name, "draft": await topic.draft()}
                self._full_article_draft.append(row)
        return self._full_article_draft

    @Logger()
    async def refine_all_drafts(self):
        tasks = []
        for topic in self.topics:
            tasks.append(topic.refine_draft_with_llm_and_save_to_google_doc())
        await asyncio.gather(*tasks)
        await self.save_topic_structure_to_google_doc()  # we call this again to update the tab with the correct draft word count

    async def _sections_from_topics(self):
        result = []
        for topic in self.topics:
            result.append({"order": topic.order, "name": topic.name, "text": await topic.text_or_draft()})
        return result

    async def sections(self):
        if self._sections is None:
            self._sections = await self._sections_from_topics()
        return self._sections

    async def sort_sections(self):
        self._sections = sorted(self._sections, key=lambda section: section["order"])
        return self._sections

    async def add_key_facts_section(self):
        self._sections.append({"order": 0.5, "name": "", "text": await self.book_generator.fact_finder.key_facts_table()})

    async def add_interesting_facts_section(self):
        interesting_facts_text = f"""## {i18n("general.interesting_facts", title=self.book_generator.settings.title)}\n\n{await self.book_generator.fact_finder.interesting_facts_list()}"""
        self._sections.append({"order": 1.5, "name": "", "text": interesting_facts_text})

    async def add_on_audible_section(self):
        self._sections.append({"order": 1.6,"name": "","text": await self.book_generator.audible_finder.on_audible_section()})

    async def add_meta_section(self):
        self._sections.append({"order": 0.1, "name":"", "text": await self.book_generator.meta_writer.meta_sections()})

    @Logger()
    async def save_full_article_to_google_doc(self):
        await self._initialize_topic_content_docs()
        await self.google_doc_final_article.initialize()
        markdown = ""
        sections = await self.sections()
        for section in sections:
            markdown += section["text"] + "\n\n"
        await self.google_doc_final_article.update_from_markdown(markdown_text=_sanitize_markdown(markdown))
        self.book_generator.settings.set("Final Article", self.google_doc_final_article.url())

    async def run(self):
        await self._initialize_topic_content_docs()
        await self.save_topic_structure_to_google_doc()
        await self.write_all_drafts()
        await self.refine_all_drafts()

        self._sections = await self._sections_from_topics()

        await self.add_key_facts_section()
        await self.add_on_audible_section()
        await self.add_interesting_facts_section()
        await self.add_meta_section()

        await self.sort_sections()



        await self.save_full_article_to_google_doc()
