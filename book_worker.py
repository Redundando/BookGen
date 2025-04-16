import asyncio
import re
from pathlib import Path

from cacherator import Cached, JSONCache
from slugify import slugify
from smart_spread import SmartSpread, SmartTab
from toml_i18n import TomlI18n, i18n

import _config
import _config as config
from audible_page import AudiblePage
from book_generator import BookGenerator
from helper import clean_string
from book_settings import BookSettings


class BookWorker(JSONCache):

    def __init__(self, asin: str | None = None, title: str | None = None, author: str | None = None, language="en", country="us"):
        self.asin = asin
        self.language = language
        self.country = country
        if asin:
            self.data_id = f"{language}_{asin}"
        else:
            self.data_id = f"{language}_{slugify(author)}_{slugify(title)}"
        self._author = author
        self._title = title
        self._audible_page: None | AudiblePage = None
        self._sheet: SmartSpread | None = None
        self._settings_tab: SmartTab | None = None
        super().__init__(data_id=f"{self.data_id}", directory="data/book_worker")
        self.bg:None|BookGenerator = None

    def audible_page(self) -> AudiblePage | None:
        if self.asin is None:
            return None
        if self._audible_page is None:
            self._audible_page = AudiblePage(bg=None, url=f"""{i18n("url.audible")}/pd/{self.asin}""")
        return self._audible_page

    async def title(self):
        if self._title is None:
            self._title = await self.audible_page().title()
        return self._title

    async def author(self):
        if self._author is None:
            self._author = await self.audible_page().author()
        return self._author

    async def sheet_identifier(self):
        return f"({self.language}) {clean_string(await self.author())[:50]} - {clean_string(await self.title())[:50]}"

    async def sheet(self):
        if self._sheet is None:
            self._sheet = SmartSpread(sheet_identifier=await self.sheet_identifier(), key_file=_config.SERVICE_ACCOUNT_KEY_FILE, clear_cache=True)
        return self._sheet

    async def settings_tab(self):
        if self._settings_tab is None:
            self._settings_tab = (await self.sheet()).tab(tab_name="Settings", data_format="dict")
        return self._settings_tab

    async def set_up_settings_tab(self):
        settings = []
        settings.append({"Key": "Title", "Value": await self.title()})
        settings.append({"Key": "Author", "Value": await self.author()})
        settings.append({"Key": "Language", "Value": self.language})
        settings.append({"Key": "Country", "Value": self.country})
        settings.append({"Key": "Num search refinements", "Value": BookSettings.DEFAULT_NUM_SEARCH_REFINEMENTS})
        settings.append({"Key": "URLs per search", "Value": BookSettings.DEFAULT_URLS_PER_SEARCH})
        settings.append({"Key": "Min Source Length", "Value": BookSettings.DEFAULT_MIN_SOURCE_LENGTH})
        settings.append({"Key": "Max Sources", "Value": BookSettings.DEFAULT_MAX_SOURCES})
        settings.append({"Key": "Min Coverage Rating", "Value": BookSettings.DEFAULT_MIN_COVERAGE_RATING})
        settings.append({"Key": "Audiobook Languages", "Value": BookSettings.DEFAULT_AUDIOBOOK_LANGUAGES})
        settings.append({"Key": "Max Audiobooks", "Value": BookSettings.DEFAULT_MAX_AUDIOBOOKS})
        (await self.settings_tab()).data = settings
        (await self.settings_tab()).write_data(overwrite_tab=False, as_table=True)

    async def initialize(self):
        await self.set_up_settings_tab()

    async def settings_url(self):
        return (await self.sheet()).url

    async def final_text_url(self):
        return self.bg.article_writer.google_doc_final_article.url()

    async def run(self):
        sheet_identifier = re.search(r'/d/([a-zA-Z0-9-_]+)', (await self.sheet()).url).group(1)
        self.bg = BookGenerator(sheet_identifier=sheet_identifier)
        await self.bg.run()

async def main():
    bw = BookWorker(asin="B0797YBP7N", language="en")
    await bw.run()

if __name__ == "__main__":
    TomlI18n.initialize(locale="en", fallback_locale="en", directory=str(Path(__file__).parent / "i18n"))
    asyncio.run(main())
