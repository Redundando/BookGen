from toml_i18n import TomlI18n, i18n
from pathlib import Path
from searcherator import Searcherator
import asyncio
import _config

async def main():
    prompt = (i18n("source_finder.search", title="Book", author="Jim"))
    search = Searcherator(
            prompt,
            num_results=10,
            language="en",
            country="US",
            api_key=_config.BRAVE_API_KEY,
        )
    #await search.print()
    result = await search.urls()
    print(result)

if __name__ == "__main__":
    TomlI18n.initialize(locale="en", fallback_locale="en", directory=str(Path(__file__).parent / "i18n"))
    asyncio.run(main())