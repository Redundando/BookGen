import asyncio
from pathlib import Path
from typing import List, TYPE_CHECKING

import yaml
from cacherator import JSONCache
from logorator import Logger
from slugify import slugify
from smartllm import AsyncLLM
from toml_i18n import i18n

import audible_page
from audible_feature_image import AudibleImage, create_audible_feature_image_tuple, save_image
from audible_page import AudiblePage
from audible_search import AudibleSearch

if TYPE_CHECKING:
    from book_generator import BookGenerator


class AudibleFinder(JSONCache):
    DEFAULT_IMAGE_DIRECTORY = "data/images/webp"

    def __init__(self, bg: "BookGenerator") -> None:
        self.product_pages: [AudiblePage] = []
        self.book_generator = bg
        self.sheet_identifier = self.book_generator.sheet_identifier
        data_id = f"{slugify(self.sheet_identifier)}"
        self._content = ""
        super().__init__(data_id=data_id,
                         directory="data/audible_finder",
                         ttl=self.book_generator.ttl,
                         clear_cache=self.book_generator.clear_cache)
        self._audible_urls = []
        self._audible_pages = []
        self._book_descriptions = []
        self._on_audible_section = ""

    @Logger()
    async def _find_audible_urls(self) -> List[str]:
        search = AudibleSearch(bg=self.book_generator)
        result = await search.product_links()
        return result

    async def audible_urls(self):
        if len(self._audible_urls) == 0:
            self._audible_urls = await self._find_audible_urls()
        return self._audible_urls

    async def audible_pages(self):
        if len(self._audible_pages) == 0:
            for url in await self.audible_urls():
                self._audible_pages.append(audible_page.AudiblePage(bg=self.book_generator, url=url))
        return self._audible_pages

    @Logger()
    async def _analyse_all_pages(self):
        semaphore = asyncio.Semaphore(40)

        async def sem_task(page):
            async with semaphore:
                return await page.run_analysis()

        tasks = [sem_task(s) for s in await self.audible_pages()]
        await asyncio.gather(*tasks)

    @Logger()
    async def _generate_descriptions_with_llm(self):
        with open(str(Path(__file__).parent / "i18n/audible_finder.summarize_products.yaml"), "r") as f:
            json_schema = yaml.safe_load(f)

        pages = self.product_pages[:self.book_generator.settings.max_audiobooks]
        information = [await p.information() for p in pages]
        article = await self.book_generator.article_writer.sections()
        prompt = i18n(
            "audible_finder.summarize_products",
            title=self.book_generator.settings.title,
            author=self.book_generator.settings.author,
            products=information,
            article=article)

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
        result = llm.response.get("audible_products")
        return result

    async def _sort_product_pages(self, pages=None):
        result = pages
        for page in result:
            page.sort = await page.num_ratings()
        result = sorted(result, key=lambda p: p.sort, reverse=True)
        return result

    async def _remove_duplicate_pages(self, pages=None):
        async def pages_are_equal(page1: AudiblePage, page2: AudiblePage):
            if await page1.title() != await page2.title(): return False
            if await page1.author() != await page2.author(): return False
            if await page1.narrators() != await page2.narrators(): return False
            if await page1.is_abridged() != await page2.is_abridged(): return False
            return True

        result = []
        for page in pages:
            is_duplicate = False
            for listed_page in result:
                if await pages_are_equal(listed_page, page): is_duplicate = True
            if not is_duplicate: result.append(page)
        return result

    async def book_descriptions(self):
        if len(self._book_descriptions) == 0:
            self._book_descriptions = await self._generate_descriptions_with_llm()
        return self._book_descriptions

    async def generate_on_audible_section(self):
        result = f"## {i18n("general.on_audible", title=self.book_generator.settings.title)}\n\n"
        for description in await self.book_descriptions():
            product_page: AudiblePage | None = None
            for page in self.product_pages:
                if description.get("asin", "") == await page.asin():
                    product_page = page
                    break
            if product_page is None:
                break
            result += f"**{description.get("asin")}**\n\n"
            abridged = f"({i18n('general.abridged_version')})" if (await product_page.is_abridged()) else ""
            result += f"- **[{await product_page.title()}]({product_page.url})** {abridged}\n"

            result += f"""- **{i18n('general.language')}**: {i18n(f"general.{await product_page.language()}")}\n"""
            result += f"- **{i18n('general.narrator')}**: {", ".join(await product_page.narrators())}\n"
            result += f"- **{i18n('general.duration')}**: {await product_page.say_duration()}\n"
            result += f"- **{i18n('general.rating')}**: {await product_page.say_rating()}\n"
            result += f"\n\n{description.get("description", "")}\n\n"
        return result

    async def on_audible_section(self):
        if self._on_audible_section == "":
            self._on_audible_section = await self.generate_on_audible_section()
        return self._on_audible_section

    @Logger()
    async def save_feature_image(self):
        file_name = slugify(f"{self.book_generator.settings.author}-{self.book_generator.settings.title}")[:100]
        urls = []
        for page in self.product_pages[:5]:
            urls.append(await page.image_url())

        if len(urls) < 5: urls = urls[:3]
        for i in range(len(urls)):
            images = [AudibleImage(image_url=url) for url in urls[:5]]
            feature_image = create_audible_feature_image_tuple(images)
            save_image(feature_image, filename=f"{file_name} ({i})", path=self.DEFAULT_IMAGE_DIRECTORY, format_="webp")
            urls = urls[-1:] + urls[:-1]

    @Logger()
    async def run(self):
        await self._analyse_all_pages()
        correct_pages = [page for page in (await self.audible_pages()) if (await page.is_correct_page_for_book())]
        sorted_pages = await self._sort_product_pages(correct_pages)
        self.product_pages = await self._remove_duplicate_pages(sorted_pages)
        self._on_audible_section = await self.generate_on_audible_section()
        await self.save_feature_image()
