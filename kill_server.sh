#!/bin/bash

PORT=$1

if [ -z "$PORT" ]; then
  echo "Usage: $0 <port>"
  exit 1
fi

PID=$(lsof -t -i:$PORT)

if [ -z "$PID" ]; then
  echo "No process found on port $PORT."
else
  echo "Killing process $PID on port $PORT."
  kill -9 $PID
  echo "Process killed."
fi