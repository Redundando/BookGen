from typing import List
import os
import json
from pathlib import Path

from logorator import Logger
import _config
from toml_i18n import TomlI18n, i18n
from book_analyzer import BookAnalyzer
from source_processor import SourceSummary
from book_finder import BookFinder

@Logger()
def setup_i18n():
    i18n_dir = Path(__file__).parent / "i18n"
    TomlI18n.initialize(locale="en", fallback_locale="en", directory=str(i18n_dir))


@Logger()
def analyze_book(book_finder, output_dir: str) -> List[SourceSummary]:
    setup_i18n()

    os.makedirs(output_dir, exist_ok=True)

    book_title = book_finder.title
    author = book_finder.author
    api_key = os.environ.get("ANTHROPIC_API_KEY", "your_api_key_here")

    analyzer = BookAnalyzer(
            book_title=book_title,
            author=author,
            api_key=api_key
    )

    summaries = analyzer.process_book(book_finder)

    output_file = Path(output_dir) / f"{book_title.lower().replace(' ', '_')}_summaries.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump([s.to_dict() for s in summaries], f, indent=2)

    Logger.note(f"Saved {len(summaries)} source summaries to {output_file}")

    return summaries


if __name__ == "__main__":
    setup_i18n()

    book_finder = BookFinder(
            title="The Hobbit",
            author="J.R.R. Tolkien"    )

    print(book_finder.get_sources_with_markdown())

    #print(book_finder.get_sources_with_markdown())
    #summaries = analyze_book(book_finder, "outputs")

    #print(f"Processed {len(summaries)} sources for '{book_finder.title}'")