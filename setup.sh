#!/bin/bash
set -e

echo ""
echo "======================================"
echo "  Expandimo — One-Time Setup"
echo "======================================"
echo ""

# Fix Homebrew permissions
echo "► Fixing Homebrew permissions..."
sudo chown -R $(whoami) /opt/homebrew

# Install PostgreSQL and Redis
echo "► Installing PostgreSQL 15..."
brew install postgresql@15

echo "► Installing Redis..."
brew install redis

# Add postgres to PATH for this session
export PATH="/opt/homebrew/opt/postgresql@15/bin:$PATH"

# Start services
echo "► Starting PostgreSQL..."
brew services start postgresql@15
sleep 3

echo "► Starting Redis..."
brew services start redis
sleep 2

# Create database and user
echo "► Setting up database..."
createuser -s expandimo 2>/dev/null || true
createdb -U expandimo expandimo_db 2>/dev/null || true
psql -U expandimo -d expandimo_db -c "ALTER USER expandimo WITH PASSWORD 'expandimo_pass';" 2>/dev/null || true

# Create .env if not exists
if [ ! -f .env ]; then
  cp .env.example .env
  echo "► Created .env file"
fi

# Update .env with local URLs (no Docker hostnames)
sed -i '' 's|postgresql+asyncpg://expandimo:expandimo_pass@db:|postgresql+asyncpg://expandimo:expandimo_pass@localhost:|g' .env
sed -i '' 's|postgresql://expandimo:expandimo_pass@db:|postgresql://expandimo:expandimo_pass@localhost:|g' .env
sed -i '' 's|redis://redis:|redis://localhost:|g' .env

# Create storage directory
mkdir -p storage/cvs

# Setup Python venv with Python 3.14
echo "► Setting up Python virtual environment..."
cd backend
/opt/homebrew/bin/python3.14 -m venv venv
source venv/bin/activate
pip install --upgrade pip -q

echo "► Installing Python dependencies (this takes a few minutes)..."
pip install fastapi uvicorn[standard] sqlalchemy[asyncio] asyncpg alembic psycopg2-binary redis celery \
  python-jose[cryptography] passlib[bcrypt] python-multipart aiofiles httpx \
  anthropic google-auth google-auth-oauthlib google-api-python-client \
  python-docx reportlab openpyxl pandas pytz holidays playwright \
  beautifulsoup4 lxml pydantic pydantic-settings python-dotenv -q

echo "► Installing Playwright browser..."
playwright install chromium 2>/dev/null || true

# Run database migrations
echo "► Running database migrations..."
export DATABASE_URL="postgresql+asyncpg://expandimo:expandimo_pass@localhost:5432/expandimo_db"
export SYNC_DATABASE_URL="postgresql://expandimo:expandimo_pass@localhost:5432/expandimo_db"
export SECRET_KEY="local-dev-secret-key-change-in-production"
export ANTHROPIC_API_KEY="placeholder"
export GMAIL_CLIENT_ID="placeholder"
export GMAIL_CLIENT_SECRET="placeholder"
alembic upgrade head
cd ..

# Install frontend dependencies
echo "► Installing frontend dependencies..."
cd frontend
npm install -q
cd ..

echo ""
echo "======================================"
echo "  Setup Complete!"
echo "======================================"
echo ""
echo "Next steps:"
echo "  1. Edit .env and add your API keys:"
echo "     - ANTHROPIC_API_KEY"
echo "     - GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET"
echo "     - APOLLO_API_KEY (optional)"
echo ""
echo "  2. Run the system:"
echo "     bash start-local.sh"
echo ""
