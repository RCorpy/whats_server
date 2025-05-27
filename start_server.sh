#!/bin/bash

# Start MongoDB (asks for your sudo password once)
echo "Starting MongoDB service..."
sudo systemctl start mongod

# Check if MongoDB started successfully
if systemctl is-active --quiet mongod; then
    echo "MongoDB started successfully."
else
    echo "Failed to start MongoDB. Please check your installation."
    exit 1
fi

# Start FastAPI server with uvicorn
echo "Starting FastAPI server..."
uvicorn main:app --host 0.0.0.0 --port 5000 --reload

