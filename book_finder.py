from typing import Dict, Any, Optional, List
from smartllm import SmartLLM
from toml_i18n import i18n
from logorator import Logger
from scraperator import Scraper
from cacherator import JSONCache, Cached
import concurrent.futures
from _config import PERPLEXITY_API_KEY
from slugify import slugify


class BookFinder(JSONCache):
    def __init__(self, title: str, author: str, model: str = "sonar-pro") -> None:
        data_id = f"{slugify(title)}-{slugify(author)}-{slugify(model)}"
        super().__init__(data_id=data_id, directory="data/book_finder")

        self.title = title
        self.author = author
        self.api_key = PERPLEXITY_API_KEY
        self.model = model
        self.max_chunk_size = 50 * 1024  # 50kB in bytes

        if not hasattr(self, "source_urls"):
            self.source_urls = []
        if not hasattr(self, "sources"):
            self.sources = []
        if not hasattr(self, "content"):
            self.content = ""

    @Logger()
    @Cached()
    def find_source_urls(self) -> List[str]:
        prompt = i18n("book_finder.search", title=self.title, author=self.author)

        llm = SmartLLM(
                base="perplexity",
                model=self.model,
                api_key=self.api_key,
                prompt=prompt,
                temperature=0.2,
                return_citations=True
        )

        llm.execute().wait_for_completion()

        if llm.is_failed():
            error = llm.get_error()
            Logger.note(f"LLM request failed: {error}")
            return []

        self.source_urls = llm.sources if hasattr(llm, "sources") else []
        self.content = llm.content if hasattr(llm, "content") else ""

        Logger.note(f"Found information about '{self.title}' with {len(self.source_urls)} sources")
        self.json_cache_save()

        return self.source_urls

    @Logger()
    @Cached()
    def download_sources(self) -> List[Dict[str, Any]]:
        # If we don't have any source URLs yet, find them first
        if not self.source_urls:
            Logger.note("No source URLs found. Running find_source_urls() first.")
            self.find_source_urls()

        if not self.source_urls:
            Logger.note("No source URLs found to download.")
            return []

        downloaded_sources = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_url = {
                    executor.submit(self._download_source, url, i): (url, i)
                    for i, url in enumerate(self.source_urls)
            }

            for future in concurrent.futures.as_completed(future_to_url):
                url, index = future_to_url[future]
                try:
                    result = future.result()
                    if result:
                        downloaded_sources.append(result)
                except Exception as e:
                    Logger.note(f"Error downloading source {url}: {str(e)}")

        self.sources = downloaded_sources
        Logger.note(f"Downloaded {len(self.sources)} sources out of {len(self.source_urls)}")

        # Save the state after downloading sources
        self.json_cache_save()

        return self.sources

    @Logger()
    @Cached()
    def _download_source(self, url: str, index: int) -> Optional[Dict[str, Any]]:
        try:
            scraper = Scraper(
                    url=url,
                    method="playwright",
                    headless=True,
                    cache_ttl=7
            )

            html = scraper.scrape()

            if not html:
                Logger.note(f"No content retrieved from {url}")
                return None

            return {
                    "url"    : url,
                    "scraper": scraper,
                    "title"  : scraper.soup.title.string if scraper.soup.title else "Unknown Title",
                    "index"  : index
            }

        except Exception as e:
            Logger.note(f"Failed to download {url}: {str(e)}")
            return None

    @Logger()
    @Cached()
    def get_sources_with_markdown(self) -> Dict[str, Dict[str, str]]:
        # If no sources have been downloaded yet, download them first
        if not self.sources:
            Logger.note("No sources downloaded yet. Running download_sources() first.")
            self.download_sources()

        result = {}

        for source in self.sources:
            if source and "scraper" in source and source["scraper"]:
                url = source["url"]
                markdown = source["scraper"].get_markdown()
                title = source["title"]

                result[url] = {
                        "markdown": markdown,
                        "title"   : title
                }

        return result

    @Logger()
    def _split_text(self, text: str) -> List[str]:
        if len(text.encode('utf-8')) <= self.max_chunk_size:
            return [text]

        # Split text into lines
        lines = text.split('\n')
        chunks = []
        current_chunk = ""

        # Helper function to check if a line is a markdown headline
        def is_headline(line: str) -> bool:
            stripped = line.strip()
            return stripped.startswith('#') and ' ' in stripped

        # Helper function to check if adding content would exceed chunk size
        def would_exceed_limit(current: str, addition: str) -> bool:
            return len((current + addition).encode('utf-8')) > self.max_chunk_size

        # Process line by line, preferring to split after headlines
        for i, line in enumerate(lines):
            # If adding this line would exceed chunk size, or if previous line was a headline
            # and current chunk is not empty and not too small
            previous_line_is_headline = i > 0 and is_headline(lines[i - 1])
            current_chunk_has_content = len(current_chunk.encode('utf-8')) > 5000  # At least 5KB

            if (would_exceed_limit(current_chunk, '\n' + line) or
                    (previous_line_is_headline and current_chunk_has_content)):

                if current_chunk:  # Don't add empty chunks
                    chunks.append(current_chunk)
                current_chunk = line
            else:
                if current_chunk:
                    current_chunk += '\n' + line
                else:
                    current_chunk = line

        # Add the last chunk if it's not empty
        if current_chunk:
            chunks.append(current_chunk)

        # If any chunk is still too large, split it further using paragraph boundaries
        final_chunks = []
        for chunk in chunks:
            if len(chunk.encode('utf-8')) > self.max_chunk_size:
                # Split by paragraphs
                paragraphs = chunk.split('\n\n')
                sub_chunk = ""

                for paragraph in paragraphs:
                    if would_exceed_limit(sub_chunk, '\n\n' + paragraph):
                        if sub_chunk:
                            final_chunks.append(sub_chunk)
                        sub_chunk = paragraph
                    else:
                        if sub_chunk:
                            sub_chunk += '\n\n' + paragraph
                        else:
                            sub_chunk = paragraph

                if sub_chunk:
                    final_chunks.append(sub_chunk)
            else:
                final_chunks.append(chunk)

        return final_chunks

    @Logger()
    @Cached()
    def get_chunked_markdown_sources(self) -> List[Dict[str, Any]]:
        # Get sources with markdown first
        sources_with_markdown = self.get_sources_with_markdown()

        chunked_sources = []

        for url, source_data in sources_with_markdown.items():
            markdown = source_data["markdown"]

            # Split the markdown into chunks if needed
            chunks = self._split_text(markdown)

            # Add each chunk to the list
            for i, chunk in enumerate(chunks):
                chunked_sources.append({
                        "url"     : url,
                        "chunk"   : i,
                        "markdown": chunk
                })

        Logger.note(f"Split sources into {len(chunked_sources)} chunks")
        return chunked_sources

    @Logger()
    def get_summary(self) -> str:
        # If we don't have content yet, try to find source URLs (which will also get the content)
        if not self.content:
            Logger.note("No content found. Running find_source_urls() first.")
            self.find_source_urls()

        return self.content