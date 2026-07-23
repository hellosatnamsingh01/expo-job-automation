#!/bin/bash
set -e

export PATH="/opt/homebrew/opt/postgresql@15/bin:$PATH"

echo ""
echo "======================================"
echo "  Starting Expandimo Automation"
echo "======================================"
echo ""

# Ensure services are running
echo "► Checking PostgreSQL..."
brew services start postgresql@15 2>/dev/null || true

echo "► Checking Redis..."
brew services start redis 2>/dev/null || true

sleep 2

# Load env
if [ ! -f .env ]; then
  echo "ERROR: .env file not found. Run setup.sh first."
  exit 1
fi
set -a; source .env; set +a

# Start Celery worker
echo "► Starting Celery worker..."
cd backend
source venv/bin/activate

celery -A app.tasks.celery_app worker --loglevel=warning \
  --detach --logfile=/tmp/expandimo_celery_worker.log \
  --pidfile=/tmp/expandimo_celery_worker.pid 2>/dev/null || true

# Start Celery beat
echo "► Starting Celery beat scheduler..."
celery -A app.tasks.celery_app beat --loglevel=warning \
  --detach --logfile=/tmp/expandimo_celery_beat.log \
  --pidfile=/tmp/expandimo_celery_beat.pid 2>/dev/null || true

# Start FastAPI
echo "► Starting backend API..."
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
cd ..

sleep 2

# Start Next.js
echo "► Starting frontend..."
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "======================================"
echo "  All services running!"
echo "======================================"
echo ""
echo "  Frontend:  http://localhost:3005"
echo "  Backend:   http://localhost:8000"
echo "  API Docs:  http://localhost:8000/docs"
echo ""
echo "  Celery logs:  /tmp/expandimo_celery_worker.log"
echo ""
echo "  Press Ctrl+C to stop frontend & backend"
echo "  (PostgreSQL & Redis keep running in background)"
echo ""

cleanup() {
  echo ""
  echo "Stopping services..."
  kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
  # Stop celery
  [ -f /tmp/expandimo_celery_worker.pid ] && kill $(cat /tmp/expandimo_celery_worker.pid) 2>/dev/null || true
  [ -f /tmp/expandimo_celery_beat.pid ] && kill $(cat /tmp/expandimo_celery_beat.pid) 2>/dev/null || true
  echo "Done."
}

trap cleanup EXIT
wait $BACKEND_PID $FRONTEND_PID
