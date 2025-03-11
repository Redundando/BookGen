
import os
from smartllm import SmartLLM
from toml_i18n import i18n
from logorator import Logger
from cacherator import JSONCache, Cached
from slugify import slugify


class SourceAnalyzer(JSONCache):
    def __init__(self, url: str, chunk: int, markdown: str,
                 further_information: str = "",
                 model: str = "claude-3-7-sonnet-20250219") -> None:
        # Create a unique ID based on the URL and chunk number
        data_id = f"source-analyzer-{slugify(url)}-chunk-{chunk}"
        super().__init__(data_id=data_id, directory="data/source_analyzer")

        self.url = url
        self.chunk = chunk
        self.markdown = markdown
        self.further_information = further_information
        self.api_key = os.environ.get("ANTHROPIC_API_KEY")
        self.model = model

        # Initialize analysis result if not already in cache
        if not hasattr(self, "analysis_result"):
            self.analysis_result = {}

        # Store the further information to track changes
        if not hasattr(self, "_cached_further_info"):
            self._cached_further_info = ""

    @Logger()
    @Cached(clear_cache=False)
    def analyze(self):
        # If further information has changed, we need to reanalyze
        if self._cached_further_info != self.further_information:
            Logger.note(f"Further information changed, reanalyzing {self.url} chunk {self.chunk}")
            self._cached_further_info = self.further_information
            self.analysis_result = self._perform_analysis()
            self.json_cache_save()
        # If we don't have results yet, perform analysis
        elif not self.analysis_result:
            Logger.note(f"No cached analysis found for {self.url} chunk {self.chunk}")
            self.analysis_result = self._perform_analysis()
            self.json_cache_save()
        else:
            Logger.note(f"Using cached analysis result for {self.url} chunk {self.chunk}")

        return self.analysis_result

    @Logger()
    def _perform_analysis(self):
        # Get the prompt from i18n
        prompt = i18n("source_analyzer.analyze_content",
                      url=self.url,
                      chunk=self.chunk,
                      further_information=self.further_information,
                      markdown=self.markdown)

        # Get the system prompt from i18n
        system_prompt = i18n("source_analyzer.system_prompt")

        json_schema = {
                "type"      : "object",
                "properties": {
                        "topics"    : {
                                "type" : "array",
                                "items": {"type": "string"}
                        },
                        "key_points": {
                                "type" : "array",
                                "items": {"type": "string"}
                        },
                        "insights"  : {
                                "type" : "array",
                                "items": {"type": "string"}
                        },
                        "entities"  : {
                                "type" : "array",
                                "items": {"type": "string"}
                        }
                },
                "required"  : ["topics", "key_points", "insights", "entities"]
        }

        # Create a SmartLLM instance
        llm = SmartLLM(
                base="anthropic",
                model=self.model,
                api_key=self.api_key,
                prompt=prompt,
                temperature=0.1,
                max_input_tokens=200_000,
                max_output_tokens=15_000,
                stream=True,
                json_mode = True,
                json_schema = json_schema
        )

        # Generate the analysis
        llm.execute().wait_for_completion()

        if llm.is_failed():
            error = llm.get_error()
            Logger.note(f"LLM analysis failed for {self.url} chunk {self.chunk}: {error}")
            return {"error": error}

        Logger.note(f"Successfully analyzed {self.url} chunk {self.chunk}")
        return llm.response