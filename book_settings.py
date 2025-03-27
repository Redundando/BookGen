from typing import TYPE_CHECKING

from cacherator import Cached, JSONCache
from slugify import slugify
import _config

if TYPE_CHECKING:
    from book_generator import BookGenerator


class BookSettings(JSONCache):
    DEFAULT_GENERAL_BASE = "anthropic"
    DEFAULT_GENERAL_MODEL = "claude-3-7-sonnet-20250219"
    DEFAULT_SEARCH_BASE = "perplexity"
    DEFAULT_SEARCH_MODEL = "sonar-pro"

    def __init__(self, bg: "BookGenerator") -> None:
        self.book_generator = bg
        self.sheet = self.book_generator.sheet
        data_id = f"{slugify(self.sheet.sheet_identifier)}"
        self.service_account_file = _config.SERVICE_ACCOUNT_KEY_FILE
        super().__init__(data_id=data_id, directory="data/book_settings", ttl=self.book_generator.ttl, clear_cache=self.book_generator.clear_cache)
        self._excluded_cache_vars = ["search_api_key"]


    @property
    @Cached()
    def _settings_tab(self):
        return self.sheet.tab(tab_name="Settings", data_format="dict")

    @property
    @Cached()
    def _settings(self):
        data = {item['Key']: item['Value'] for item in self._settings_tab.data}
        result = {key.strip().lower().replace(' ', '_'): value for key, value in data.items()}
        return result

    @property
    def title(self):
        return self._settings.get("title", None)

    @property
    def author(self):
        return self._settings.get("author", None)

    @property
    def search_base(self):
        return self._settings.get("search_base", self.DEFAULT_SEARCH_BASE)

    @property
    def search_model(self):
        return self._settings.get("search_model", self.DEFAULT_SEARCH_MODEL)

    @property
    def search_api_key(self):
        return self._settings.get("search_api_key", "")

    @property
    def email(self):
        return self._settings.get("share_email", None)

    @property
    def general_base(self):
        return self._settings.get("general_base", self.DEFAULT_GENERAL_BASE)

    @property
    def general_model(self):
        return self._settings.get("general_model", self.DEFAULT_GENERAL_MODEL)

    @property
    def min_source_length(self):
        return int(self._settings.get("min_source_length", self.DEFAULT_GENERAL_MODEL))

    @property
    def final_article_url(self):
        return self._settings.get("final_article", None)

    def set(self, key="", value=""):
        self._settings_tab.update_row_by_column_pattern(column="Key", value=key, updates={"Value": value})
        self._settings_tab.write_data()

    @property
    def general_api_key(self):
        result = self._settings.get("general_api_key", "")
        if result == "":
            import os
            result = os.environ.get("ANTHROPIC_API_KEY")
        return result