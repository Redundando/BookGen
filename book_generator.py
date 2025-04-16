import asyncio
from pathlib import Path

from cacherator import Cached, JSONCache
from slugify import slugify
from smart_spread import SmartSpread
from toml_i18n import TomlI18n

import _config as config
import article_writer
import book_settings
import source_finder
import topic_finder
import fact_finder
import audible_finder
import meta_writer

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
    def sources(self):
        return self.source_finder.source_contents

    @property
    @Cached()
    def topic_finder(self):
        return topic_finder.TopicFinder(bg=self)

    @property
    @Cached()
    def fact_finder(self):
        return fact_finder.FactFinder(bg=self)

    @property
    @Cached()
    def audible_finder(self):
        return audible_finder.AudibleFinder(bg=self)

    @property
    @Cached()
    def meta_writer(self):
        return meta_writer.MetaWriter(bg=self)


    @property
    @Cached()
    def article_writer(self):
        return article_writer.ArticleWriter(bg=self)

    async def topics(self):
        return await self.article_writer.topics

    async def run(self):
        TomlI18n.initialize(locale=self.settings.language, fallback_locale="en", directory=str(Path(__file__).parent / "i18n"))
        await self.source_finder.run()
        await self.topic_finder.run()
        await self.audible_finder.run()
        await self.article_writer.run()



async def main():
    # darius = BookGenerator(sheet_identifier="1oFqIAaPjAdsbxmrhInJS7Cnp5OOFc9BByZl2dc-AuME", clear_cache=False)
    # madonna = BookGenerator(sheet_identifier="1g3Cf6N0-8Mh_O0Nd3Rufq3WrAC5mzQikZftnXLtqZAU", clear_cache=False)
    # tadzio = BookGenerator(sheet_identifier="1tW-Pbbq6pJ908LFtRaahvtiV2DX7bzLm1_heSDDK7U8", clear_cache=False)
    # demian = BookGenerator(sheet_identifier="1T5iww2OoBP_oxwL6rAEa4TtKOo2D0s44JbV-mX91ZMM")
    # cats = BookGenerator(sheet_identifier="1mciIdQdovAsyxFeuGnzxvjqpLOtOCymofuk-swGv11k", clear_cache=False)
    # minds = BookGenerator(sheet_identifier="18FUR96CoCmKafrgoiZ0qzPSGeQv4nsHnOANil_-qfXk", clear_cache=True)
    # mom = BookGenerator(sheet_identifier="1Luzg3NKFbnlfLmnvxitbMakumxL7d-cLJ5q2JLsvJBk", clear_cache=True)
    # dante = BookGenerator(sheet_identifier="1jEipXyvvful3B6XMFSkjnOuNbQhlhc_aSiHyD0-JwHo")
    # none = BookGenerator(sheet_identifier="1wfJKf8BV4Nw-pmVg3zKZd3dqrJkiURG9yR9ohq2eJsY")
    # nathan = BookGenerator(sheet_identifier="1p0lAElQa0RxhTaPhq8okOhbyK-lnjSHR7kzCMCeo_LM", clear_cache=False)
    # it = BookGenerator(sheet_identifier="12-zYmGVMoL4f-GG8RWafPcviB6lGoY84zPI0OjE8zGI")
    # mind = BookGenerator(sheet_identifier="1133H4NgWjZHSw4Tdu74bDVX8iZ4M9Urf6Gjiueyr-xo")
    # giovanni = BookGenerator(sheet_identifier="1h8rmkpk0mlJ5ltfkFIGJJAWkDwn4EndA1jP6ejrKXyo")
    # dschinns = BookGenerator(sheet_identifier="15Lak0d3OQzBtuYiBJo1b80m1GdBt-OhOyrJvsHiiCfo", clear_cache=False)
    # welt = BookGenerator(sheet_identifier="1RUQniXmt6TBE-It5SktaDGedFZXkStBpA4Bs8WopNRM", clear_cache=False)
    # pinky = BookGenerator(sheet_identifier="1Yxj636li7BBBZf0kkepLU6lF9D_0gNQM-ZMaBDrvhuQ", clear_cache=False)
    # orwell = BookGenerator(sheet_identifier="1sD6aVxlUpytrdcnugPb40eR4ObY4tCAjWH3kavkkO5Q")
    # anders = BookGenerator(sheet_identifier="1LxrgsfsA5-pRKGwRPFxahgL3yAzLG_NVUtYvTrKo4LI")
    # zeh = BookGenerator(sheet_identifier="1qGsRGOp6kM2OoQvyIse_InmKHPfE2NK1wjHuluo7K_A")
    # nef = BookGenerator(sheet_identifier="1UYxtgU_cHtcLE_Eh7lAZOfvu3hJ-Yqj3fPxQgXeGrws")
    bilbo = BookGenerator(sheet_identifier="1KUhA6z-D5SToWX-AK02sVhoNDBjRiLigrlFKLazMT3E")
    await bilbo.run()



if __name__ == "__main__":
    asyncio.run(main())
