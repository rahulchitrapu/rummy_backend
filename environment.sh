source /venv/bin/activate
export FLASK_APP=app.main
export FLASK_ENV=development

# Load environment variables from .env file
if [ -f .env ]; then
    export $(cat .env | grep -v '#' | xargs)
fi