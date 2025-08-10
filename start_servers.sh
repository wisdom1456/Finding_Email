#!/bin/bash

# Grant execution permissions to the kill script
chmod +x kill_server.sh

# Kill any existing processes on ports 8000 and 8501
echo "Shutting down old server processes..."
./kill_server.sh 8000
./kill_server.sh 8501

# Load environment variables from .env file
if [ -f .env ]; then
  export $(cat .env | xargs)
fi

# Start the FastAPI backend in the background
echo "Starting FastAPI backend server..."
cd backend
nohup uvicorn main:app --reload --port 8000 > backend.log 2>&1 &
cd ..

# Start the Streamlit frontend
echo "Starting Streamlit frontend server..."
streamlit run app.py --server.port 8501

echo "Servers are starting. Please check the terminal for output."
