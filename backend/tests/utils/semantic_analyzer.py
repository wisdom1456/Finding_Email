import openai
import os
from dotenv import load_dotenv

load_dotenv()

class SemanticAnalyzer:
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key not found. Please set the OPENAI_API_KEY environment variable.")
        openai.api_key = self.api_key

    def get_semantic_similarity(self, text1, text2):
        """
        Calculates semantic similarity between two texts using OpenAI's embeddings.
        """
        try:
            response1 = openai.Embedding.create(input=[text1], model="text-embedding-ada-002")
            response2 = openai.Embedding.create(input=[text2], model="text-embedding-ada-002")
            
            embedding1 = response1['data'][0]['embedding']
            embedding2 = response2['data'][0]['embedding']
            
            # Simple cosine similarity
            import numpy as np
            similarity = np.dot(embedding1, embedding2) / (np.linalg.norm(embedding1) * np.linalg.norm(embedding2))
            
            return similarity
        except openai.error.OpenAIError as e:
            print(f"An OpenAI error occurred: {e}")
            return 0.0

    def analyze_tone(self, text):
        """
        Analyzes the tone of a given text.
        (This is a placeholder and would likely use a classification model)
        """
        try:
            # For demonstration, this is a mock. A real implementation
            # would use a proper tone analysis model or a prompted completion.
            prompt = f"Analyze the tone of the following text and return the primary tone and a confidence score. Text: '{text}'"
            response = openai.Completion.create(
                model="text-davinci-003",
                prompt=prompt,
                max_tokens=20
            )

            # NOTE: This parsing is simplistic and depends on a consistent response format.
            # A more robust solution is needed for production.
            result_text = response.choices[0].text.strip()
            # Example mock parsing: "Tone: Professional, Score: 0.85"
            parts = result_text.split(',')
            tone = parts[0].split(':')[1].strip()
            score = float(parts[1].split(':')[1].strip())

            return {"label": tone, "score": score}

        except openai.error.OpenAIError as e:
            print(f"An OpenAI error occurred during tone analysis: {e}")
            return None
        except Exception as e:
            # Fallback for parsing or other errors
            print(f"An error occurred during tone analysis: {e}")
            # A mock response for demonstration purposes
            if "formal" in text.lower():
                 return {"label": "Formal", "score": 0.9}
            else:
                 return {"label": "Casual", "score": 0.8}
