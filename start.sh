#!/bin/bash
# RAGMind Quick Start Script

echo "🧠 RAGMind — Self-Healing RAG Platform"
echo "======================================="

# Check if .env exists
if [ ! -f "backend/.env" ]; then
  echo "⚠️  backend/.env not found. Copying from .env.example..."
  cp backend/.env.example backend/.env
  echo "📝 Please edit backend/.env and add your GROQ_API_KEY"
  echo "   Get a free key at: https://console.groq.com"
  exit 1
fi

echo ""
echo "Starting backend..."
cd backend
python -m venv venv 2>/dev/null || true
source venv/bin/activate 2>/dev/null || venv\Scripts\activate 2>/dev/null || true
pip install -r requirements.txt -q
python main.py &
BACKEND_PID=$!
cd ..

echo "Starting frontend..."
cd frontend
npm install -q
npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "✅ RAGMind is running!"
echo "   Frontend: http://localhost:5173"
echo "   Backend:  http://localhost:8000"
echo "   API Docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop..."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo 'Stopped.'" INT
wait
