from __future__ import annotations

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()

import numpy as np


class SemanticAnalyzer:
    def __init__(self, client=None, api_key=None):
        # Accept an OpenAI client or create one
        if client is not None:
            self.client = client
        else:
            if not api_key:
                from backend_logic.config import get_openai_api_key

                try:
                    api_key = get_openai_api_key()
                except ValueError:
                    api_key = None
            if not api_key:
                msg = "OpenAI API key not found. Please set the OPENAI_API_KEY environment variable."
                raise ValueError(
                    msg
                )
            self.client = OpenAI(api_key=api_key)

    def get_semantic_similarity(self, text1, text2):
        """
        Calculates semantic similarity between two texts using OpenAI's embeddings (>=1.0.0 API).
        """
        try:
            response1 = self.client.embeddings.create(
                input=[text1], model="text-embedding-ada-002"
            )
            response2 = self.client.embeddings.create(
                input=[text2], model="text-embedding-ada-002"
            )
            embedding1 = response1.data[0].embedding
            embedding2 = response2.data[0].embedding

            # Simple cosine similarity
            return np.dot(embedding1, embedding2) / (
                np.linalg.norm(embedding1) * np.linalg.norm(embedding2)
            )
        except Exception as e:
            print(f"An error occurred during embedding similarity: {e}")
            return 0.0

    def analyze_tone(self, text):
        """
        Analyzes the tone of a given text using OpenAI chat completions (>=1.0.0 API).
        """
        try:
            system_message = {
                "role": "system",
                "content": "You are a tone analysis assistant. Given a text, respond with the primary tone and a confidence score in the format: 'Tone: <label>, Score: <score>'.",
            }
            user_message = {
                "role": "user",
                "content": f"Analyze the tone of the following text and return the primary tone and a confidence score. Text: '{text}'",
            }
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[system_message, user_message],
                max_tokens=20,
                temperature=0.0,
            )
            result_text = response.choices[0].message.content.strip()
            # Example mock parsing: "Tone: Professional, Score: 0.85"
            parts = result_text.split(",")
            tone = parts[0].split(":")[1].strip()
            score = float(parts[1].split(":")[1].strip())
            return {"label": tone, "score": score}
        except Exception as e:
            print(f"An error occurred during tone analysis: {e}")
            # A mock response for demonstration purposes
            if "formal" in text.lower():
                return {"label": "Formal", "score": 0.9}
            return {"label": "Casual", "score": 0.8}
