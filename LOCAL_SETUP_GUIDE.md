# 🖥️ Local Development Setup Guide for NyayaVoice

This guide will help you run NyayaVoice on your local machine using VS Code.

---

## ✅ Prerequisites

- ✅ **Python 3.11+** — You have Python 3.13.7 ✓
- ✅ **VS Code** — Installed
- ✅ **Git** — Installed ✓

---

## 📦 Step 1: Open Project in VS Code

1. **Open VS Code**
2. **File** → **Open Folder**
3. Navigate to: `C:\Users\DELL\Downloads\NyayaVoice\Hackathon`
4. Click **Select Folder**

---

## 🐍 Step 2: Create Virtual Environment

**Why?** Keeps project dependencies isolated from your system Python.

### Option A: Using VS Code Terminal

1. Open Terminal in VS Code: **Terminal** → **New Terminal** (or `` Ctrl+` ``)
2. Run:
   ```powershell
   python -m venv venv
   ```
3. Wait for it to complete (~30 seconds)

### Option B: Using Command Palette

1. Press `Ctrl+Shift+P`
2. Type: `Python: Create Environment`
3. Select **Venv**
4. Select your Python interpreter (Python 3.13.7)

---

## 🔌 Step 3: Activate Virtual Environment

### In VS Code Terminal:

```powershell
.\venv\Scripts\Activate.ps1
```

**Expected output:**
```
(venv) PS C:\Users\DELL\Downloads\NyayaVoice\Hackathon>
```

**Note:** You should see `(venv)` at the start of your terminal prompt.

### If you get an execution policy error:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Then try activating again.

---

## 📥 Step 4: Install Dependencies

With the virtual environment activated:

```powershell
pip install -r requirements.txt
```

**This will install:**
- FastAPI (web framework)
- Uvicorn (ASGI server)
- Qdrant Client (vector database)
- FastEmbed (embedding model - ~50MB download on first run)
- ReportLab (PDF generation)
- And other dependencies

**Expected time:** 2-3 minutes

---

## 🔑 Step 5: Create Environment Variables File

Create a `.env` file in the `Hackathon` folder:

```powershell
Copy-Item .env.example .env
```

Then edit `.env` with your keys:

```env
# Vapi keys (OPTIONAL - only needed for voice calls)
VAPI_API_KEY=your_vapi_api_key_here
VAPI_PUBLIC_KEY=your_vapi_public_key_here

# Qdrant (leave as :memory: for local development)
QDRANT_URL=:memory:
QDRANT_API_KEY=

# Backend URL (for local development)
BACKEND_URL=http://localhost:8000
```

**For now, you can leave the Vapi keys as placeholders.** The app will work without them (text chat only).

---

## 🚀 Step 6: Start the Development Server

### Method 1: Using the start script (Recommended)

```powershell
bash start.sh
```

**If bash is not available, use Method 2.**

### Method 2: Direct uvicorn command

```powershell
$env:PYTHONPATH = (Get-Location).Path
uvicorn main:app --reload --port 8000
```

**Expected output:**
```
🚀 Starting NyayaVoice Legal Aid Assistant...
==================================================
📦 Installing Python dependencies...
🔍 Checking Qdrant connection...
ℹ️  Using in-memory Qdrant
📁 Creating directories...

🌟 Starting uvicorn server on port 8000...

INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

---

## 🌐 Step 7: Open the Application

1. **Open your browser**
2. Go to: **http://localhost:8000**
3. You should see the NyayaVoice landing page

### Additional URLs:

- **API Documentation:** http://localhost:8000/docs (Swagger UI)
- **Alternative API Docs:** http://localhost:8000/redoc
- **Health Check:** http://localhost:8000/health

---

## 🧪 Step 8: Test the Application

### Test 1: Health Check

In a new terminal (keep the server running):

```powershell
curl http://localhost:8000/health
```

**Expected response:**
```json
{"status":"ok","service":"NyayaVoice API"}
```

### Test 2: Text Chat

1. Click **Get Started** on the landing page
2. Click **Ask Legal Help** in the sidebar
3. Type a question like: "My phone was stolen, how do I file an FIR?"
4. Press Enter or click Send

### Test 3: FIR Wizard

1. Click **FIR Wizard** in the sidebar
2. Fill in the form step by step
3. Click **Generate FIR PDF**
4. Download the generated PDF

---

## 🛠️ VS Code Extensions (Recommended)

Install these extensions for better development experience:

1. **Python** (Microsoft) — Python language support
2. **Pylance** (Microsoft) — Fast Python language server
3. **Python Debugger** (Microsoft) — Debugging support
4. **REST Client** — Test API endpoints directly in VS Code

### To install:

1. Press `Ctrl+Shift+X` to open Extensions
2. Search for each extension
3. Click **Install**

---

## 🐛 Debugging in VS Code

### Step 1: Create launch configuration

1. Click **Run and Debug** icon in sidebar (or press `Ctrl+Shift+D`)
2. Click **create a launch.json file**
3. Select **Python**
4. Select **FastAPI**

### Step 2: Edit `.vscode/launch.json`

```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Python: FastAPI",
            "type": "debugpy",
            "request": "launch",
            "module": "uvicorn",
            "args": [
                "main:app",
                "--reload",
                "--port",
                "8000"
            ],
            "jinja": true,
            "justMyCode": true,
            "env": {
                "PYTHONPATH": "${workspaceFolder}"
            }
        }
    ]
}
```

### Step 3: Set breakpoints and debug

1. Click in the left margin of any Python file to set a breakpoint (red dot)
2. Press `F5` to start debugging
3. The server will start and pause at your breakpoints

---

## 📁 Project Structure

```
Hackathon/
├── backend/
│   ├── routes/          # API endpoints
│   │   ├── query.py     # /api/query
│   │   ├── document.py  # /api/generate-document
│   │   └── memory.py    # /api/store-memory, /api/recall-memory
│   ├── services/        # Business logic
│   │   ├── qdrant.py    # Vector database operations
│   │   ├── llm.py       # Response generation (no external LLM needed)
│   │   └── document_gen.py  # PDF generation
│   ├── scripts/         # Utility scripts
│   │   └── seed_legal_data.py  # Legal knowledge seeding
│   └── config.py        # Configuration
├── frontend/            # Static frontend files
│   ├── index.html       # Main HTML
│   ├── app.js           # JavaScript logic
│   ├── styles.css       # Styling
│   └── i18n.js          # Translations (English + Hindi)
├── generated_docs/      # Generated PDFs (auto-created)
├── main.py              # FastAPI application entry point
├── requirements.txt     # Python dependencies
├── .env                 # Environment variables (you create this)
├── .env.example         # Environment variables template
└── start.sh             # Startup script
```

---

## 🔄 Making Changes

### Backend Changes (Python)

1. Edit any `.py` file
2. Save the file (`Ctrl+S`)
3. Uvicorn will **auto-reload** (if using `--reload` flag)
4. Refresh your browser to see changes

### Frontend Changes (HTML/CSS/JS)

1. Edit `frontend/index.html`, `app.js`, or `styles.css`
2. Save the file
3. **Hard refresh** your browser: `Ctrl+Shift+R` (or `Ctrl+F5`)

---

## 🛑 Stopping the Server

In the terminal where the server is running:

- Press `Ctrl+C`
- Wait for graceful shutdown

---

## 🧹 Common Issues & Solutions

### Issue 1: Port 8000 already in use

**Error:**
```
ERROR: [Errno 10048] error while attempting to bind on address ('0.0.0.0', 8000)
```

**Solution:**
```powershell
# Find process using port 8000
netstat -ano | findstr :8000

# Kill the process (replace PID with actual process ID)
taskkill /PID <PID> /F

# Or use a different port
uvicorn main:app --reload --port 8080
```

### Issue 2: Module not found

**Error:**
```
ModuleNotFoundError: No module named 'fastapi'
```

**Solution:**
```powershell
# Make sure virtual environment is activated
.\venv\Scripts\Activate.ps1

# Reinstall dependencies
pip install -r requirements.txt
```

### Issue 3: Virtual environment activation fails

**Error:**
```
cannot be loaded because running scripts is disabled on this system
```

**Solution:**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Issue 4: FastEmbed model download fails

**Error:**
```
Failed to download embedding model
```

**Solution:**
The app will automatically fall back to hash-based embeddings (no download needed). This works fine for development.

### Issue 5: Frontend shows blank page

**Solution:**
1. Check browser console for errors (`F12`)
2. Verify server is running on port 8000
3. Hard refresh: `Ctrl+Shift+R`
4. Check that `BACKEND_URL` in `.env` is `http://localhost:8000`

---

## 📊 Viewing Logs

### Server logs

All logs appear in the terminal where you started the server.

### Application logs

Check `logs/` folder (auto-created) for detailed logs.

---

## 🔧 Advanced: Using Qdrant Cloud (Optional)

If you want persistent storage instead of in-memory:

1. Sign up at [cloud.qdrant.io](https://cloud.qdrant.io)
2. Create a free cluster
3. Copy your Cluster URL and API Key
4. Update `.env`:
   ```env
   QDRANT_URL=https://your-cluster.qdrant.io
   QDRANT_API_KEY=your_api_key
   ```
5. Restart the server

---

## 🎤 Adding Voice Call Support (Optional)

1. Sign up at [vapi.ai](https://vapi.ai)
2. Use promo code `vapixhackblr` for $30 free credits
3. Get your API keys from Dashboard
4. Update `.env`:
   ```env
   VAPI_API_KEY=your_actual_key
   VAPI_PUBLIC_KEY=your_actual_public_key
   ```
5. Restart the server
6. Voice button will now work on the dashboard

---

## 🎉 You're All Set!

Your NyayaVoice development environment is ready. Happy coding! 🚀

### Quick Start Commands (After Initial Setup)

```powershell
# Navigate to project
cd C:\Users\DELL\Downloads\NyayaVoice\Hackathon

# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Start server
uvicorn main:app --reload --port 8000

# Open browser
start http://localhost:8000
```

---

## 📚 Additional Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com)
- [Qdrant Documentation](https://qdrant.tech/documentation/)
- [VS Code Python Tutorial](https://code.visualstudio.com/docs/python/python-tutorial)

---

**Need help?** Check the troubleshooting section above or open an issue on GitHub.
