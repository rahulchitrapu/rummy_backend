#!/bin/bash

# Run the Rummy Backend application

# Load environment
source environment.sh

echo "Starting Rummy Backend server..."
echo "Server will be available at http://localhost:5000"

# Run the application
python app/main.py


# source environment.sh
# gunicorn --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker -w 1 -b 0.0.0.0:5000 app.main:app
