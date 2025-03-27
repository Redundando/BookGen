from pathlib import Path
import asyncio
from cacherator import Cached, JSONCache
from slugify import slugify
from smart_spread import SmartSpread
from tldextract.tldextract import update
from toml_i18n import TomlI18n

import _config as config
import article_writer
import book_settings
import source_finder
import topic_finder


def setup_toml18n():
    TomlI18n.initialize(locale="en", fallback_locale="en", directory=str(Path(__file__).parent / "i18n"))


class BookGenerator(JSONCache):

    def __init__(self, sheet_identifier="", ttl=7, clear_cache=False):
        self.sheet_identifier = sheet_identifier
        self.service_account_key = config.SERVICE_ACCOUNT_KEY
        super().__init__(data_id=f"{slugify(self.sheet_identifier)}", ttl=ttl, clear_cache=clear_cache, directory="data/book_generator")
        self.ttl = ttl
        self.clear_cache = clear_cache
        self._excluded_cache_vars = ["api_key", "service_account_key"]

    @property
    @Cached()
    def sheet(self) -> SmartSpread:
        return SmartSpread(sheet_identifier=self.sheet_identifier, service_account_data=self.service_account_key)

    @property
    @Cached()
    def settings(self):
        return book_settings.BookSettings(bg=self)

    @property
    @Cached()
    def source_finder(self):
        return source_finder.SourceFinder(bg=self)

    @property
    @Cached()
    def sources(self):
        return self.source_finder.source_contents

    @property
    @Cached()
    def topic_finder(self):
        return topic_finder.TopicFinder(bg=self)

    @property
    @Cached()
    def article_writer(self):
        return article_writer.ArticleWriter(bg=self)

    async def topics(self):
        return await self.topic_finder.topics()

    async def run(self):
        await self.source_finder.scrape_all_sources()
        await self.source_finder.save_source_information_urls()
        await self.source_finder.analyse_all_sources()
        await self.topic_finder.synthesize_sources()
        await self.article_writer.write_all_drafts()
        await self.article_writer.refine_all_drafts()
        await self.article_writer.save_full_article_to_google_doc()

    async def refine_topic(self, i):
        topics = await self.topics()
        topic = topics[i]
        return await topic._refine_topic_with_llm()

async def main():
    setup_toml18n()
    #darius = BookGenerator(sheet_identifier="1oFqIAaPjAdsbxmrhInJS7Cnp5OOFc9BByZl2dc-AuME", clear_cache=False)
    #tadzio = BookGenerator(sheet_identifier="1feDCEKGi2AFHt6kw5-nntrvJTNFM_1GpzzrEvc6QGrU", clear_cache=False)
    #minds = BookGenerator(sheet_identif/ier="18FUR96CoCmKafrgoiZ0qzPSGeQv4nsHnOANil_-qfXk", clear_cache=False)
    #mom = BookGenerator(sheet_identifier="1Luzg3NKFbnlfLmnvxitbMakumxL7d-cLJ5q2JLsvJBk", clear_cache=True)
    #dante = BookGenerator(sheet_identifier="1jEipXyvvful3B6XMFSkjnOuNbQhlhc_aSiHyD0-JwHo")
    none = BookGenerator(sheet_identifier="1wfJKf8BV4Nw-pmVg3zKZd3dqrJkiURG9yR9ohq2eJsY")


    await none.run()

if __name__ == "__main__":
    asyncio.run(main())