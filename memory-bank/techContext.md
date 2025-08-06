# Tech Context

## Development Environment

The Legal Document Analysis Portal is built on a unified Streamlit-Python stack, which provides a modern, efficient, and maintainable development environment.

### Core Technologies

*   **Framework**: Streamlit - A Python-based web framework that enables rapid application development and deployment.
*   **Language**: Python 3.12+ - The application is written in modern Python, with a focus on type hints and asynchronous support.
*   **Data Models**: Pydantic is used for data validation and creating structured data models, ensuring robustness and consistency.

### Key Dependencies

The application relies on a curated set of libraries to handle its core functionality:

*   **Streamlit**: The foundation of the web application.
*   **OpenAI**: For all AI-powered analysis and content generation.
*   **Google Cloud**: The application uses the `google-cloud-aiplatform` and `google-cloud-speech` libraries for advanced video and audio processing.
*   **Document Processors**: A suite of libraries, including `python-docx`, `PyPDF2`, and `pyth`, is used for handling various document formats.
*   **Image and Audio**: `Pillow` and `pydub` are used for image and audio manipulation.
*   **Token Management**: The `tiktoken` library is used for accurate token counting, which is critical for the video data preservation system.

## Deployment

The unified Streamlit application is designed for straightforward deployment on modern hosting platforms.

*   **Platform**: The application is optimized for deployment on Streamlit Cloud, but it can also be containerized with Docker for deployment on other platforms like Railway or Heroku.
*   **Environment Configuration**: All configuration, including API keys and Google Cloud credentials, is managed through a single `.env` file, which is loaded at runtime using the `python-dotenv` library.

## Google Cloud Integration

The application's advanced video processing capabilities are powered by Google Cloud.

*   **Project Setup**: A Google Cloud project with the Vertex AI, Speech-to-Text, and Cloud Storage APIs enabled is required.
*   **Service Account**: A properly configured service account with the necessary IAM roles (`Vertex AI User`, `Storage Object Admin`, `Speech Service Agent`) is used for authentication.
*   **Bucket Configuration**: A dedicated Cloud Storage bucket with a 24-hour lifecycle policy is used for temporary video file storage.