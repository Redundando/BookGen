import os
from itertools import chain
from typing import TYPE_CHECKING

from cacherator import JSONCache
from logorator import Logger
from slugify import slugify

if TYPE_CHECKING:
    from book_generator import BookGenerator

from pathlib import Path
from toml_i18n import i18n
import yaml

from smartllm import AsyncLLM, SmartLLM


class FactFinder(JSONCache):

    def __init__(self, bg: "BookGenerator") -> None:
        self.book_generator = bg
        self.sheet_identifier = self.book_generator.sheet_identifier
        data_id = f"{slugify(self.sheet_identifier)}"
        self._content = ""
        super().__init__(data_id=data_id,
                         directory="data/fact_finder",
                         ttl=self.book_generator.ttl,
                         clear_cache=self.book_generator.clear_cache)

    @property
    def sources(self):
        return self.book_generator.sources

    async def _all_interesting_facts(self):
        source_facts = [await s.interesting_facts() for s in self.sources]
        flat_list = list(chain.from_iterable(source_facts))
        return flat_list

    @Logger()
    async def _synthesize_interesting_facts(self):
        with open(str(Path(__file__).parent / "i18n/fact_finder.synthesize_interesting_facts.yaml"), "r") as f:
            json_schema = yaml.safe_load(f)
        prompt = i18n(
            "fact_finder.synthesize_facts",
            title=self.book_generator.settings.title,
            author=self.book_generator.settings.author,
            facts=await self._all_interesting_facts())
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

        result = llm.response.get("interesting_facts", [])
        return result

    @Logger()
    async def _get_key_facts(self):
        prompt = i18n(
            "fact_finder.get_key_facts",
            title=self.book_generator.settings.title,
            author=self.book_generator.settings.author)
        llm = SmartLLM(base="perplexity",
                       model="sonar-pro",
                       api_key=os.environ.get("PERPLEXITY_API_KEY"),
                       prompt=prompt)
        llm.execute()
        return llm.response

    @Logger()
    async def _organize_key_facts(self):
        with open(str(Path(__file__).parent / "i18n/fact_finder.organize_key_facts.yaml"), "r") as f:
            json_schema = yaml.safe_load(f)
            print(json_schema)

        prompt = i18n(
            "fact_finder.organize_key_facts",
            title=self.book_generator.settings.title,
            author=self.book_generator.settings.author,
            facts=await self._get_key_facts())

        llm = AsyncLLM(
            base=self.book_generator.settings.general_base,
            model=self.book_generator.settings.general_model,
            api_key=self.book_generator.settings.general_api_key,
            prompt=prompt,
            temperature=0.2,
            max_input_tokens=200_000,
            max_output_tokens=50_000,
            json_mode=True,
            json_schema=json_schema)
        await llm.execute()

        result = llm.response
        return result

    @Logger()
    async def key_facts(self):
        result = await self._organize_key_facts()
        result["author"] = self.book_generator.settings.author
        result["title"] = self.book_generator.settings.title
        return result

    async def key_facts_table(self):
        facts = await self.key_facts()
        result = ""
        result += f"""- **{i18n("general.title")}**: {facts.get("title", "")}\n"""
        result += f"""- **{i18n("general.author")}**: {facts.get("author", "")}\n"""
        if "first_published" in facts: result += f"""- **{i18n("general.first_published")}**: {facts.get("first_published", "")}\n"""
        genres = [str(genre) for genre in facts.get("genres", [])]
        if "genres" in facts: result += f"""- **{i18n("general.genres")}**: {", ".join(genres)}\n"""
        if "temporal_setting" in facts: result += f"""- **{i18n("general.temporal_setting")}**: {facts.get("temporal_setting", "")}\n"""
        main_themes = [str(theme).title() for theme in facts.get("main_themes", [])]
        if "main_themes" in facts: result += f"""- **{i18n("general.themes")}**: {", ".join(main_themes)}\n"""
        return result

    async def interesting_facts_list(self):
        result = ""
        facts = await self._synthesize_interesting_facts()
        for fact in facts:
            result += f"- {fact}\n"
        return result
