from typing import List
import os
import json
from pathlib import Path

from logorator import Logger
import _config
from toml_i18n import TomlI18n, i18n
from book_finder import BookFinder
from source_analyzer import SourceAnalyzer

@Logger()
def setup_i18n():
    #i18n_dir =
    TomlI18n.initialize(locale="en", fallback_locale="en", directory=str(Path(__file__).parent / "i18n"))


if __name__ == "__main__":
    setup_i18n()

    book_finder = BookFinder(
            title="The Hobbit",
            author="J.R.R. Tolkien"    )

    print(book_finder.find_source_urls())

    info = book_finder.get_sources_with_markdown()

    #print(info)

    #sa = SourceAnalyzer(url=info["url"], chunk=info["chunk"], markdown=info["markdown"])
    #print(sa.analyze())
