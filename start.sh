#!/bin/bash
set -e

echo "=== Expandimo Automation System ==="
echo ""

# Check .env
if [ ! -f .env ]; then
  cp .env.example .env
  echo "✓ Created .env from .env.example — please fill in your API keys!"
  echo ""
fi

echo "Starting PostgreSQL + Redis via Docker..."
docker compose up -d db redis
echo "Waiting for database to be ready..."
sleep 5

echo "Installing Python dependencies..."
cd backend
python3 -m venv venv 2>/dev/null || true
source venv/bin/activate
pip install -r requirements.txt -q

echo "Running database migrations..."
alembic upgrade head

echo "Starting Celery worker..."
celery -A app.tasks.celery_app worker --loglevel=warning --detach --logfile=/tmp/celery_worker.log --pidfile=/tmp/celery_worker.pid

echo "Starting Celery beat scheduler..."
celery -A app.tasks.celery_app beat --loglevel=warning --detach --logfile=/tmp/celery_beat.log --pidfile=/tmp/celery_beat.pid

echo "Starting FastAPI backend..."
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
cd ..

echo "Installing frontend dependencies..."
cd frontend
npm install -q

echo "Starting Next.js frontend..."
npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "=== All services started ==="
echo "  Frontend:  http://localhost:3005"
echo "  Backend:   http://localhost:8000"
echo "  API Docs:  http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; docker compose stop db redis" EXIT
wait
