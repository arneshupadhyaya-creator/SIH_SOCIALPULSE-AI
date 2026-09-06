# 🌐 Audience Intelligence — AI Research & Telemetry Studio

> **Production-grade Social Media Audience Intelligence & Real-Time Telemetry Platform**  
> Collect, translate, analyze sentiments & emotions, identify demographic patterns, and uncover influence networks on public social media data.

---

## 📑 Table of Contents

- [✨ Key Features](#-key-features)
- [⚡ Quick Start: The Easiest Way (Docker)](#-quick-start-the-easiest-way-docker)
- [💻 Manual Setup: Running Locally with Python](#-manual-setup-running-locally-with-python)
  - [Prerequisites](#prerequisites)
  - [Step 1: Clone the Repository](#step-1-clone-the-repository)
  - [Step 2: Create & Activate Virtual Environment](#step-2-create--activate-virtual-environment)
  - [Step 3: Install Dependencies](#step-3-install-dependencies)
  - [Step 4: Download spaCy Language Model](#step-4-download-spacy-language-model)
  - [Step 5: Configure Environment Variables (.env)](#step-5-configure-environment-variables-env)
  - [Step 6: Setup Database & Run Migrations](#step-6-setup-database--run-migrations)
  - [Step 7: Launch the Web Application](#step-7-launch-the-web-application)
- [🔑 Setting Up Scraper Accounts (accounts.txt)](#-setting-up-scraper-accounts-accountstxt)
- [🖥️ Accessing the Application](#️-accessing-the-application)
- [❓ Beginner Troubleshooting & FAQs](#-beginner-troubleshooting--faqs)
- [🏗️ Project Architecture & Tech Stack](#️-project-architecture--tech-stack)

---

## ✨ Key Features

- **Interactive Telemetry Web Studio**: High-performance dashboard with glassmorphic UI, real-time analytics, charts, and network graphs.
- **Resilient Data Ingestion**: Multi-account rotation pool, automated cookie handling, rate-limit protection, and circuit breakers.
- **Sentiment & Emotion Classification**: Advanced NLP transformers classifying joy, anger, sadness, fear, surprise, and sentiment polarity.
- **Multilingual Pipeline**: Automatic translation of non-English posts into English for unified analysis.
- **Topic Modeling & Trend Detection**: BERTopic-powered semantic clustering and rolling-window trend spike detection.
- **Entity & Demographics Extraction**: spaCy-powered entity recognition for locations, age indicators, and user traits.
- **Network & Community Detection**: NetworkX and Louvain modularity to discover influencers and audience clusters.

---

## ⚡ Quick Start: The Easiest Way (Docker)

If you have **Docker Desktop** installed, this is the single fastest and easiest way to run the entire project (database + backend + web UI) with one command.

### 1. Prerequisites
- Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) (ensure Docker Desktop is running).
- Install [Git](https://git-scm.com/).

### 2. Clone and Start
Open your terminal (PowerShell, Command Prompt, or Terminal) and run:

```bash
# 1. Clone the repository and enter the SIH directory
git clone https://github.com/BHAVYAGUPTA727/SIH-PS-26152.git
cd SIH-PS-26152/SIH

# 2. Start everything in Docker
docker compose up --build
```

> 📌 *Note: If you have already opened the project directly in the `SIH` folder, you can simply run `docker compose up --build` immediately.*

That's it! Once you see the logs showing `Application startup complete`, open your browser and go to:
👉 **[http://localhost:8000](http://localhost:8000)**

To stop the containers later, press `Ctrl + C` or run:
```bash
docker compose down
```

---

## 💻 Manual Setup: Running Locally with Python

Follow this step-by-step guide if you want to run the project directly on your machine without Docker.

### Prerequisites

Ensure you have the following installed on your computer:
1. **Python 3.10 or 3.11**: [Download Python](https://www.python.org/downloads/)  
   *(⚠️ On Windows, check the box **"Add Python to PATH"** during installation!)*
2. **Git**: [Download Git](https://git-scm.com/)
3. **PostgreSQL / TimescaleDB**: [Download PostgreSQL](https://www.postgresql.org/download/)  
   *(Default user `postgres` with password `postgres` and a database named `audience_intel`).*

---

### Step 1: Clone the Repository

Open your terminal or command line and run:

```bash
git clone https://github.com/BHAVYAGUPTA727/SIH-PS-26152.git
cd SIH-PS-26152/SIH
```
> 📌 *Note: If you already have your terminal open inside the `SIH` project directory, you are ready to proceed to Step 2.*

---

### Step 2: Create & Activate Virtual Environment

A virtual environment keeps all dependencies isolated and prevents system conflicts.

#### On Windows (PowerShell):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```
> 💡 *If you get an `Execution_Policies` script error in PowerShell, run this command first:*
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
> ```
> *Then run `.\.venv\Scripts\Activate.ps1` again.*

#### On Windows (Command Prompt - CMD):
```cmd
python -m venv .venv
.\.venv\Scripts\activate.bat
```

#### On macOS / Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

You will see `(.venv)` displayed at the start of your terminal line when activated.

---

### Step 3: Install Dependencies

With your virtual environment activated, run:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

### Step 4: Download spaCy Language Model

The NLP pipeline requires the English demographic entity model:

```bash
python -m spacy download en_core_web_sm
```

---

### Step 5: Configure Environment Variables (.env)

Make a copy of the example configuration file:

#### On Windows:
```cmd
copy .env.example .env
```

#### On macOS / Linux:
```bash
cp .env.example .env
```

Open `.env` in any text editor (VS Code, Notepad, etc.). If your local PostgreSQL uses a different password or port, update the credentials:
```ini
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/audience_intel
SYNC_DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/audience_intel
```

---

### Step 6: Setup Database & Run Migrations

Make sure your PostgreSQL service is running and a database named `audience_intel` exists:

```bash
# In PostgreSQL CLI (psql):
CREATE DATABASE audience_intel;
```

Then apply database migrations to generate all required tables:

```bash
alembic upgrade head
```

---

### Step 7: Launch the Web Application

Start the FastAPI development server:

```bash
uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload
```

---

## 🔑 Setting Up Scraper Accounts (accounts.txt)

To fetch live posts from X (Twitter), configure account credentials in an `accounts.txt` file (never commit this file to GitHub):

1. Make a copy of `accounts.example.txt` named `accounts.txt`:
   ```bash
   # Windows:
   copy accounts.example.txt accounts.txt

   # Mac/Linux:
   cp accounts.example.txt accounts.txt
   ```
2. Open `accounts.txt` and add your scraper accounts (one per line):
   ```text
   # Recommended format (cookie-based):
   username:password:email:email_password:cookies=auth_token=YOUR_AUTH_TOKEN;ct0=YOUR_CT0
   ```
   > ⚠️ **Note:** Always use dedicated burner accounts for scraping. Do NOT use personal accounts.

---

## 🖥️ Accessing the Application

Once the server is running, open your web browser to access:

| Destination | URL | Description |
|---|---|---|
| 🎨 **Web Studio Dashboard** | `http://localhost:8000/` | Main interactive user interface |
| 📖 **Interactive API Docs** | `http://localhost:8000/docs` | Swagger UI for executing and testing API endpoints |
| 🩺 **System Health** | `http://localhost:8000/health` | Service health status and circuit breaker state |

---

## ❓ Beginner Troubleshooting & FAQs

### 1. "Port 8000 is already in use"
Another application or previous instance is running on port 8000.
- Change the port when launching:
  ```bash
  uvicorn api.main:app --host 127.0.0.1 --port 8080 --reload
  ```
- Or terminate whatever is using port 8000:
  - **Windows**: `netstat -ano | findstr :8000` then `taskkill /PID <PID> /F`
  - **Mac/Linux**: `lsof -i :8000` then `kill -9 <PID>`

### 2. "Database connection refused"
- Make sure PostgreSQL is started on your computer or the Docker database container is running.
- Verify credentials in `.env` match your local PostgreSQL username, password, and port.

### 3. "ModuleNotFoundError: No module named 'spacy'"
Ensure your virtual environment `(.venv)` is activated before running python or uvicorn commands.

### 4. "Script execution is disabled on this system" (PowerShell)
Run PowerShell as Administrator or run within your current session:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
```

---

## 🏗️ Project Architecture & Tech Stack

```text
├── api/                  # FastAPI web server, routes, and controllers
│   └── main.py           # Application entrypoint & static frontend mount
├── web/                  # Frontend UI Studio
│   ├── index.html        # Glassmorphic dashboard interface
│   ├── style.css         # Modern design tokens, animations, and layouts
│   └── app.js            # Client-side analytics, API polling, and charts
├── analytics/            # NLP, Demographics, Emotions, and Graph algorithms
│   ├── emotion_classifier.py
│   ├── translator.py
│   ├── demographics.py
│   ├── topics.py
│   └── network.py
├── ingestion/            # Scraper client, account pool, and rate limiters
├── db/                   # Database models, schemas, and Alembic migrations
├── docker-compose.yml    # Full-stack container orchestration
├── Dockerfile            # Container image specification
└── requirements.txt      # Python dependencies
```

---

## 📄 License
This project is developed for the Smart India Hackathon (SIH) Problem Statement PS-26152.
