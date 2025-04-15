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


class MetaWriter(JSONCache):

    def __init__(self, bg: "BookGenerator"):
        self.book_generator = bg
        self.lead_in = ""
        JSONCache.__init__(
                self,
                data_id=f"{self.book_generator.settings.author} - {self.book_generator.settings.title}",
                directory="data/meta",
                ttl=self.book_generator.ttl,
                clear_cache=self.book_generator.clear_cache)

    async def _write_lead_in_with_llm(self):
        with open(str(Path(__file__).parent / "i18n/audible_page.analyse.yaml"), "r") as f:
            json_schema = yaml.safe_load(f)

        sections = await self.book_generator.article_writer.sections()
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