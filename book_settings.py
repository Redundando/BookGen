from typing import TYPE_CHECKING
import os
from cacherator import Cached, JSONCache
from slugify import slugify

import _config

if TYPE_CHECKING:
    from book_generator import BookGenerator


class BookSettings(JSONCache):
    DEFAULT_GENERAL_BASE = "openai"
    DEFAULT_GENERAL_MODEL = "gpt-4o"
    DEFAULT_GENERAL_API_KEY = os.environ.get("CHATGPT_API_KEY")
    DEFAULT_COMPLEX_BASE = "openai"
    DEFAULT_COMPLEX_MODEL = "gpt-4.5-preview"
    DEFAULT_COMPLEX_API_KEY = os.environ.get("CHATGPT_API_KEY")
    DEFAULT_WRITING_BASE = "openai"
    DEFAULT_WRITING_MODEL = "gpt-4o"
    DEFAULT_WRITING_API_KEY = os.environ.get("CHATGPT_API_KEY")
    DEFAULT_SEARCH_BASE = "perplexity"
    DEFAULT_SEARCH_MODEL = "sonar-pro"
    DEFAULT_SEARCH_API_KEY = os.environ.get("PERPLEXITY_API_KEY")

    DEFAULT_BRAVE_API_KEY = os.environ.get("BRAVE_API_KEY")


    DEFAULT_ARTICLE_TYPE = "short"
    DEFAULT_MIN_SOURCE_LENGTH = 1500
    DEFAULT_NUM_SEARCH_REFINEMENTS = 7
    DEFAULT_URLS_PER_SEARCH = 14
    DEFAULT_MIN_COVERAGE_RATING = 7
    DEFAULT_MAX_SOURCES = 80
    DEFAULT_AUDIOBOOK_LANGUAGES = "english"
    DEFAULT_MAX_AUDIOBOOKS = 5

    DEFAULT_SOURCE_SCRAPE_TIMEOUT = 20
    DEFAULT_SOURCE_SCRAPE_RETRIES = 3

    DEFAULT_AUDIBLE_SCRAPE_TIMEOUT = 30
    DEFAULT_AUDIBLE_SCRAPE_RETRIES = 3

    def __init__(self, bg: "BookGenerator") -> None:
        self.book_generator = bg
        self.sheet = self.book_generator.sheet
        data_id = f"{slugify(self.sheet.sheet_identifier)}"
        self.service_account_file = _config.SERVICE_ACCOUNT_KEY_FILE
        super().__init__(data_id=data_id, directory="data/book_settings", ttl=self.book_generator.ttl, clear_cache=True)
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
    def language(self):
        return self._settings.get("language", "en")

    @property
    def country(self):
        return self._settings.get("country", "US").upper()

    @property
    def article_type(self):
        return self._settings.get("article_type", self.DEFAULT_ARTICLE_TYPE)

    @property
    def article_type_key(self):
        return f"article_type.{self.article_type}"

    @property
    def proposed_word_count(self):
        try:
            return int(self._settings.get("proposed_word_count", 0))
        except:
            return 0

    @property
    def word_count_is_set(self):
        return self.proposed_word_count > 0

    @property
    def search_base(self):
        return self._settings.get("search_base", self.DEFAULT_SEARCH_BASE)

    @property
    def search_model(self):
        return self._settings.get("search_model", self.DEFAULT_SEARCH_MODEL)

    @property
    def search_api_key(self):
        return self._settings.get("search_api_key", self.DEFAULT_SEARCH_API_KEY)

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
    def general_api_key(self):
        return self._settings.get("general_api_key", self.DEFAULT_GENERAL_API_KEY)

    @property
    def complex_base(self):
        return self._settings.get("complex_base", self.DEFAULT_COMPLEX_BASE)

    @property
    def complex_model(self):
        return self._settings.get("complex_model", self.DEFAULT_COMPLEX_MODEL)

    @property
    def complex_api_key(self):
        return self._settings.get("complex_api_key", self.DEFAULT_COMPLEX_API_KEY)

    @property
    def writing_base(self):
        return self._settings.get("writing_base", self.DEFAULT_WRITING_BASE)

    @property
    def writing_model(self):
        return self._settings.get("writing_model", self.DEFAULT_WRITING_MODEL)

    @property
    def writing_api_key(self):
        return self._settings.get("writing_api_key", self.DEFAULT_WRITING_API_KEY)

    @property
    def min_source_length(self):
        return int(self._settings.get("min_source_length", self.DEFAULT_MIN_SOURCE_LENGTH))

    @property
    def urls_per_search(self):
        return int(self._settings.get("urls_per_search", self.DEFAULT_URLS_PER_SEARCH))

    @property
    def num_search_refinements(self):
        return int(self._settings.get("num_search_refinements", self.DEFAULT_NUM_SEARCH_REFINEMENTS))

    @property
    def final_article_url(self):
        return self._settings.get("final_article", None)

    @property
    def min_coverage_rating(self):
        try:
            return int(self._settings.get("min_coverage_rating", self.DEFAULT_MIN_COVERAGE_RATING))
        except ValueError:
            return 7

    @property
    def max_sources(self):
        try:
            return int(self._settings.get("max_sources", self.DEFAULT_MAX_SOURCES))
        except ValueError:
            return 80

    @property
    def audiobook_languages(self):
        languages_string = self._settings.get("audiobook_languages", self.DEFAULT_AUDIOBOOK_LANGUAGES)
        languages = [l.strip() for l in languages_string.split(",")]
        return languages

    @property
    def max_audiobooks(self):
        try:
            return int(self._settings.get("max_audiobooks", self.DEFAULT_MAX_AUDIOBOOKS))
        except ValueError:
            return self.DEFAULT_MAX_AUDIOBOOKS

    def set(self, key="", value=""):
        self._settings_tab.update_row_by_column_pattern(column="Key", value=key, updates={"Value": value})
        self._settings_tab.write_data()

    @property
    def source_scrape_timeout(self):
        return int(self._settings.get("source_scrape_timeout", self.DEFAULT_SOURCE_SCRAPE_TIMEOUT))

    @property
    def source_scrape_retries(self):
        return int(self._settings.get("source_scrape_retries", self.DEFAULT_SOURCE_SCRAPE_RETRIES))

    @property
    def audible_scrape_timeout(self):
        return int(self._settings.get("audible_scrape_timeout", self.DEFAULT_AUDIBLE_SCRAPE_TIMEOUT))

    @property
    def audible_scrape_retries(self):
        return int(self._settings.get("audible_scrape_retries", self.DEFAULT_AUDIBLE_SCRAPE_RETRIES))