import asyncio
from pathlib import Path

from cacherator import Cached, JSONCache
from slugify import slugify
from smart_spread import SmartSpread
from toml_i18n import TomlI18n
from book_worker import BookWorker
import traceback
import _config as config


class AsinListWorker(JSONCache):

    def __init__(self, sheet_identifier=""):
        self.sheet_identifier = sheet_identifier
        self.service_account_key = config.SERVICE_ACCOUNT_KEY
        super().__init__(data_id=f"{self.sheet_identifier}", directory="data/asin_list_worker")

    @property
    @Cached()
    def sheet(self) -> SmartSpread:
        return SmartSpread(sheet_identifier=self.sheet_identifier, service_account_data=self.service_account_key)

    @property
    @Cached()
    def data_tab(self):
        return self.sheet.tab(tab_name="ASINs", data_format="dict")

    def open_asins(self):
        return [row for row in self.data_tab.data if row.get("Done", None) == 0]

    async def run_row(self, row):
        asin = row.get("ASIN")
        bw = BookWorker(asin=asin, language=row.get("Language", None), country=row.get("Country", None))
        await bw.initialize()
        row["Author"] = await bw.author()
        row["Title"] = await bw.title()
        row["Settings"] = await bw.settings_url()
        self.data_tab.update_row_by_column_pattern(column="ASIN", value=asin, updates=row)
        self.data_tab.write_data()
        await bw.run()
        row["Text"] = await bw.final_text_url()
        row["Done"] = 1
        self.data_tab.update_row_by_column_pattern(column="ASIN", value=asin, updates=row)
        self.data_tab.write_data()

    async def run(self):
        open_asin_rows = self.open_asins()
        for row in open_asin_rows[:1]:
            try:
                await self.run_row(row)
            except Exception as e:
                error = f"{str(e)} \n\n {traceback.format_exc()}"

                row["Exception"] = error
                row["Done"] = -1
                self.data_tab.update_row_by_column_pattern(column="ASIN", value=row.get("ASIN"), updates=row)
                self.data_tab.write_data()


async def main():
    en = AsinListWorker(sheet_identifier="1m41zxMXB9KZSNkkZq01hXqudmqrlwttgneh-uy-d4yU")
    de = AsinListWorker(sheet_identifier="1zoeh2JvUvak45yvXz_jqGafKHCAlosMCphFiYpJUqYQ")
    await de.run()
    #tab = alw.sheet.tab(tab_name="ASINs", data_format="dict")
    #print(alw.open_asins())


if __name__ == "__main__":
    TomlI18n.initialize(locale="en", fallback_locale="en", directory=str(Path(__file__).parent / "i18n"))
    asyncio.run(main())
