from setuptools import find_packages, setup

setup(
    name="legal-portal",
    version="0.1.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.8",
    install_requires=[
        "streamlit",
        "openai",
        "python-dotenv",
        "pyyaml",
        "requests",
        # Add other dependencies as needed
    ],
)
