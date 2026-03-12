#!/bin/bash

# Run the Rummy Backend application

# Load environment
source environment.sh

echo "Starting Rummy Backend server..."
echo "Server will be available at http://localhost:5000"

# Run the application
python app/main.py