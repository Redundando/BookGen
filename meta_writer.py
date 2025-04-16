import random
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from logorator import Logger
from smartllm import AsyncLLM
from toml_i18n import i18n

if TYPE_CHECKING:
    from book_generator import BookGenerator

from cacherator import JSONCache


class MetaWriter(JSONCache):

    def __init__(self, bg: "BookGenerator"):
        self.book_generator = bg
        JSONCache.__init__(
                self,
                data_id=f"{self.book_generator.settings.author} - {self.book_generator.settings.title}",
                directory="data/meta",
                ttl=self.book_generator.ttl,
                clear_cache=self.book_generator.clear_cache)
        self._meta_data: dict | None = None

    @Logger()
    async def _generate_with_llm(self):
        with open(str(Path(__file__).parent / "i18n/meta_writer.generate.yaml"), "r") as f:
            json_schema = yaml.safe_load(f)
        sections = await self.book_generator.article_writer.sections()
        prompt = i18n(
                "meta_writer.generate",
                title=self.book_generator.settings.title,
                author=self.book_generator.settings.author,
                article=sections,
                first_letter=random.choice(["a", "b", "d", "e", "f", "g", "h", "l", "m", "n", "p", "r", "s", "t"]))
        llm = AsyncLLM(
                base=self.book_generator.settings.writing_base,
                model=self.book_generator.settings.writing_model,
                api_key=self.book_generator.settings.writing_api_key,
                prompt=prompt,
                temperature=0.2,
                max_input_tokens=200_000,
                max_output_tokens=50_000,
                json_mode=True,
                json_schema=json_schema)
        await llm.execute()
        self._meta_data = llm.response
        self.json_cache_save()
        return self._meta_data

    async def meta_data(self):
        if self._meta_data is None:
            self._meta_data = await self._generate_with_llm()
        return self._meta_data

    async def meta_title(self):
        return (await self.meta_data()).get("meta_title", "")

    async def meta_description(self):
        return (await self.meta_data()).get("meta_description", "")

    async def lead_in(self):
        return (await self.meta_data()).get("lead_in", "")

    async def meta_sections(self):
        result = f"# {await self.meta_title()} \n\n"
        result += f"**{i18n('general.meta_description')}**: {await self.meta_description()}\n\n"
        result += f"**{i18n('general.lead_in')}**: {await self.lead_in()}\n\n"
        return result
