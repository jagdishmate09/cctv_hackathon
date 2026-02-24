# CCTV Hackathon – Production Deploy

This folder contains deployment config used on this server.

## What’s deployed

- **App URL:** http://140.238.163.237 (use your server IP)
- **Backend:** Gunicorn on 127.0.0.1:5000 (systemd `cctv-backend`)
- **Frontend:** Built static files in `/var/www/cctv`, served by nginx
- **Nginx:** Listens on port 80, proxies `/api/` and `/auth/` to the backend

## Files

- `cctv-backend.service` – systemd unit for the Flask backend
- `nginx-cctv.conf` – nginx site config (root `/var/www/cctv`)

## After code changes

1. **Backend:**  
   `cd backend && git pull && source venv/bin/activate && pip install -r requirements.txt`  
   Then: `sudo systemctl restart cctv-backend`

2. **Frontend:**  
   `cd frontend && git pull && npm install && VITE_API_URL= npm run build`  
   Then: `sudo cp -r dist/* /var/www/cctv/`

3. **Env:**  
   Edit `backend/.env` (e.g. Microsoft SSO, `REDIRECT_URI`, `FRONTEND_URL`) and restart:  
   `sudo systemctl restart cctv-backend`

## Microsoft SSO

Login requires Azure AD. In `backend/.env` set:

- `MICROSOFT_CLIENT_ID`
- `MICROSOFT_CLIENT_SECRET`
- `MICROSOFT_TENANT_ID`
- `REDIRECT_URI=http://YOUR_SERVER_IP/auth/microsoft/callback`
- `FRONTEND_URL=http://YOUR_SERVER_IP`
- `SECRET_KEY` (strong random value)

In Azure Portal → App registration → Authentication, add redirect URI:  
`http://YOUR_SERVER_IP/auth/microsoft/callback`
