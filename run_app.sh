#!/bin/bash

# Helper script to run the Streamlit app with correct Python path
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"

echo "Starting Streamlit app with PYTHONPATH: $PYTHONPATH"
streamlit run app/main.py "$@"
