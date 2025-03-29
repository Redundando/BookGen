import asyncio
from typing import TYPE_CHECKING

from cacherator import JSONCache
from logorator import Logger
from slugify import slugify
from docorator import Docorator

if TYPE_CHECKING:
    from book_generator import BookGenerator


def _sanitize_markdown(markdown:str= ""):
    return markdown.replace("```","").replace("markdown","")


class ArticleWriter(JSONCache):

    def __init__(self, bg: "BookGenerator") -> None:
        self.book_generator = bg
        self.sheet = self.book_generator.sheet
        data_id = f"{slugify(self.sheet.sheet_identifier)}"
        super().__init__(data_id=data_id, directory="data/article_writer", ttl=self.book_generator.ttl, clear_cache=self.book_generator.clear_cache)
        self._initialized = False

        self.google_doc_final_article = Docorator(
                service_account_file=self.book_generator.settings.service_account_file,
                document_name=f"Article {slugify(self.book_generator.settings.author)} {slugify(self.book_generator.settings.title)}",
                clear_cache=self.book_generator.clear_cache)


    @property
    def topics_tab(self):
        return self.book_generator.topic_finder.topics_tab

    async def topics(self):
        return await self.book_generator.topic_finder.topics()

    async def _initialize_topic_content_docs(self):
        if self._initialized:
            return
        tasks = []
        for topic in (await self.topics()):
            tasks.append(topic.initialize())
        await asyncio.gather(*tasks)
        self.initialized = True

    @Logger(override_function_name="Saving Topics to Google Doc")
    async def save_topic_structure_to_google_doc(self):
        await self._initialize_topic_content_docs()
        topics = (await self.topics())
        tab = self.topics_tab
        tab.data = [["Order", "Topic", "Details", "Suggested Length", "Sources", "Draft URL", "Draft Word Count","Refined Text URL", "Refined Text Word Count"]]
        for topic in topics:
            row = []
            row.append(topic.order)
            row.append(topic.name)
            row.append(topic.details)
            row.append(topic.suggested_length)
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
        await self._initialize_topic_content_docs()
        topics = (await self.topics())
        await self.save_topic_structure_to_google_doc()
        tasks = []
        for topic in topics:
            tasks.append(topic.write_draft_with_llm_and_save_to_google_doc())
        await asyncio.gather(*tasks)
        await self.save_topic_structure_to_google_doc()  # we call this again to update the tab with the correct draft word count

    async def full_text_or_draft(self):
        await self._initialize_topic_content_docs()
        result = []
        topics = (await self.topics())
        for topic in topics:
            row = {"order": topic.order, "topic": topic.name, "draft": await topic.text_or_draft()}
            result.append(row)
        return result

    @Logger()
    async def refine_all_drafts(self):
        await self._initialize_topic_content_docs()
        topics = (await self.topics())
        for topic in topics:
            if (await topic.refined_text_word_count()) < 10:
                await topic.refine_draft_with_llm_and_save_to_google_doc()
        await self.save_topic_structure_to_google_doc()

    @Logger()
    async def save_full_article_to_google_doc(self):
        await self._initialize_topic_content_docs()
        await self.google_doc_final_article.initialize()
        markdown = ""
        for topic in (await self.topics()):
            markdown += (await topic.text_or_draft()) + "\n\n"
        await self.google_doc_final_article.update_from_markdown(markdown_text=_sanitize_markdown(markdown))
        self.book_generator.settings.set("Final Article", self.google_doc_final_article.url())