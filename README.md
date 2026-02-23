# CCTV Hackathon

Installation and setup guide for the CCTV Hackathon project (backend + frontend).

---

## Prerequisites

- **Python 3.8+** (for backend)
- **Node.js 18+** and **npm** (for frontend)
- **FFmpeg** (optional but required for **.dav** Dahua CCTV files): [Download FFmpeg](https://ffmpeg.org/download.html) and add it to your PATH.
- **Tesseract OCR** (optional, for **video date/time** from CCTV OSD): [Download Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) and add it to your PATH. If not installed, the app still runs; the “Video date / time” field will show “—”.

---

## 1. Backend setup

### 1.1 Create virtual environment (if not already created)

From the project root:

**Windows (PowerShell):**
```powershell
cd backend
python -m venv venv
```

**Linux / macOS / Git Bash:**
```bash
cd backend
python3 -m venv venv
```

### 1.2 Activate virtual environment

**Windows (PowerShell):**
```powershell
.\venv\Scripts\Activate.ps1
```

**Windows (Command Prompt):**
```cmd
.\venv\Scripts\activate.bat
```

**Linux / macOS / Git Bash:**
```bash
source venv/bin/activate
```

### 1.3 Install dependencies

With the virtual environment activated (you should see `(venv)` in your prompt):

```bash
pip install -r requirements.txt
```

**Tip:** If install fails (e.g. building opencv), upgrade pip first: `python -m pip install --upgrade pip`, then run the above again.

### 1.4 Start the backend server

From the `backend` folder, with the venv activated:

```bash
python app.py
```

The API will run (by default) at **http://127.0.0.1:5000**.  
Check health: **http://127.0.0.1:5000/api/health**

---

## 2. Frontend setup

### 2.1 Install dependencies

From the project root:

```bash
cd frontend
npm install
```

### 2.2 Start the frontend dev server

From the `frontend` folder:

```bash
npm run dev
```

The app will run (typically) at **http://localhost:5173** (Vite default).

---

## 3. Running both together

1. **Terminal 1 – Backend**
   - `cd backend`
   - Activate venv (see 1.2)
   - `python app.py`

2. **Terminal 2 – Frontend**
   - `cd frontend`
   - `npm run dev`

Then open the frontend URL (e.g. http://localhost:5173) in your browser.  
Ensure the backend URL in the frontend (e.g. in env or config) matches where the backend runs (e.g. http://127.0.0.1:5000).

---

## 4. Microsoft SSO (required for login)

Login uses **Microsoft SSO only** (no username/password). Configure these in `backend/.env` (copy from `backend/.env.example`):

| Variable | Description |
|----------|-------------|
| `MICROSOFT_CLIENT_ID` | Application (client) ID from your Azure App registration |
| `MICROSOFT_CLIENT_SECRET` | Client secret from Azure → Certificates & secrets |
| `MICROSOFT_TENANT_ID` | Azure AD tenant ID, or `common` for multi-tenant |
| `REDIRECT_URI` | Must match Azure (e.g. `http://localhost:5000/auth/microsoft/callback`) |
| `FRONTEND_URL` | Frontend URL after login (e.g. `http://localhost:5173`) |
| `SECRET_KEY` | Strong random secret for signing session tokens (change in production) |

**Azure setup:** Azure Portal → Azure Active Directory → App registrations → New registration. Under **Authentication**, add a Web redirect URI: `http://localhost:5000/auth/microsoft/callback`. Under **Certificates & secrets**, create a client secret and set the variables above.

- Frontend: use `.env` in `frontend/` for `VITE_API_URL` if your API is not at `http://localhost:5000`.

---

## Quick reference

| Step              | Location  | Command (Windows PowerShell) |
|-------------------|-----------|------------------------------|
| Backend venv      | `backend` | `python -m venv venv`        |
| Activate venv     | `backend` | `.\venv\Scripts\Activate.ps1`|
| Backend deps      | `backend` | `pip install -r requirements.txt` |
| Start backend     | `backend` | `python app.py`              |
| Frontend deps     | `frontend`| `npm install`                |
| Start frontend    | `frontend`| `npm run dev`                |
