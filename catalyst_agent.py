import json
from ddgs import DDGS
from openai import OpenAI

class CatalystAgent:
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key) if api_key else None

    def fetch_recent_news(self, ticker: str) -> list[str]:
        query = f"{ticker} stock news earnings partnership catalyst"
        snippets = []
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=4))
                for r in results:
                    snippets.append(f"- {r['title']}: {r['body']}")
        except Exception as e:
            snippets.append(f"Could not fetch news: {e}")
        return snippets

    def analyze_catalyst_and_theme(self, ticker: str, news: list[str], setups: list[str]) -> dict:
        if not self.client:
            return {
                "score": "N/A",
                "catalyst_summary": "No OpenAI API Key provided. Manual news inspection required.",
                "theme": "Unknown"
            }

        news_text = "\n".join(news)
        setups_text = ", ".join(setups)

        prompt = f"""
You are a lead position/growth trader analyzing momentum stocks (Connor Bates $50M Fund Model).
Analyze the recent news for stock symbol: {ticker}.

Detected Technical Setups: {setups_text}
Recent News Snippets:
{news_text}

Respond in valid JSON format with the following keys:
- "catalyst_type": (e.g., "Earnings Beat & Raise", "Government Contract", "Regulatory Approval", "No Clear Catalyst")
- "catalyst_summary": A concise summary (in Norwegian) of the catalyst and news event.
- "theme_or_sector": What overall macro theme/narrative does this belong to (e.g., AI Infrastructure, Nuclear Energy, Space, Defense, Special Commodities)?
- "score_1_to_10": An integer rating (1-10) assessing the potential for a multi-month institutional run.
"""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.2
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            return {"error": f"LLM Analysis failed: {e}"}
