# Relay delivery partner attendance

A full-stack attendance and earnings application for delivery partners and administrators. Delivery partners can check in and out, record their daily pickups and completed deliveries, and review their attendance history. Administrators can review team totals and date-filtered individual reports.

## Requirements

- Python 3.10 or newer
- Node.js 18 or newer with npm

## Run locally on Windows

Open two PowerShell terminals in the project folder.

### 1. Start the Flask API

```powershell
cd server
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:ADMIN_EMAIL = "admin@example.com"
$env:ADMIN_PASSWORD = "ChooseAUniquePassword123!"
$env:SECRET_KEY = "replace-this-with-a-long-random-secret"
python app.py
```

If PowerShell blocks virtual-environment activation, run the environment's interpreter directly instead:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

The API listens on `http://127.0.0.1:5000`. The SQLite database is created automatically in `server/instance/attendance.sqlite3`. The first startup creates the administrator account using `ADMIN_EMAIL` and `ADMIN_PASSWORD`. The API refuses to start unless you provide a valid admin email and a password of at least 10 characters. Keep these credentials and `SECRET_KEY` private, and use a unique long admin password and secret outside local development.

### 2. Start the React app

In a second terminal, from the project folder:

```powershell
cd frontend
npm install
npm run dev
```

Open the local URL printed by Vite (usually `http://localhost:5173`). The Vite development server proxies `/api` requests to Flask.

Delivery partners register and sign in with their email address. The administrator signs in with the configured `ADMIN_EMAIL` and `ADMIN_PASSWORD`.

For an existing database, the API adds the email field automatically without deleting accounts or attendance. The existing administrator account is associated with the configured `ADMIN_EMAIL`. Existing delivery partners can still sign in with their old username; newly registered partners use their email address.

## Earnings and attendance rules

- The rate is fixed at **₹15 per completed delivery**.
- Pickups are tracked separately and never add to earnings.
- Check-in is once per partner per calendar day. A second check-in is rejected.
- Check-out requires a check-in and can happen once per day.
- Delivery counts can be updated during an active shift. They are locked after check-out.
- Daily, lifetime, overall, and individual earnings are calculated from completed deliveries.

## Run the backend tests

From `server/` with the Python dependencies installed:

```powershell
python -m unittest -v
```

## Production build

From `frontend/`:

```powershell
npm run build
```

## Free public deployment on PythonAnywhere

PythonAnywhere currently offers a limited free Beginner account with **one public web app** at `YOUR_USERNAME.pythonanywhere.com`. Its free account has usage limits and restricted outbound internet access; this small app uses a local SQLite file and does not require outbound API calls. Review the [current free-account details and limits](https://www.pythonanywhere.com/pricing/) before signing up. Home-directory files persist between web-app reloads, but keep your own database backup.

The repository includes the prebuilt React files under `frontend/dist/`, so the host does not need Node.js or npm. After rebuilding the frontend, commit the updated `frontend/dist/` files as well.

1. Create a [PythonAnywhere Beginner account](https://www.pythonanywhere.com/registration/register/beginner/), then open its **Consoles** tab and start a **Bash** console.
2. Clone the public project and install the Flask dependencies:

   ```bash
   git clone https://github.com/asunm131921220296/HTML-Workout.git
   cd HTML-Workout
   python3.13 -m venv .venv
   .venv/bin/pip install -r server/requirements.txt
   ```

3. Open the **Web** tab, choose **Add a new web app → Manual configuration**, and select Python 3.13. Do not choose the Flask quickstart: this repository already has its own Flask application.
4. In the web app's **Virtualenv** field, enter:

   ```text
   /home/YOUR_USERNAME/HTML-Workout/.venv
   ```

5. Click the WSGI configuration-file link in the Web tab. Replace its contents with `server/pythonanywhere_wsgi.py.example` and edit every `YOUR_USERNAME` occurrence to your PythonAnywhere username.
6. In that WSGI file on PythonAnywhere (not in the GitHub repository), replace `ADMIN_PASSWORD` with a strong, private password of at least 10 characters. Generate a separate `SECRET_KEY` in the Bash console with:

   ```bash
   python3.13 -c "import secrets; print(secrets.token_hex(32))"
   ```

   Copy the generated value into the WSGI file's `SECRET_KEY` setting. Never commit the edited WSGI file or share the password/secret.
7. Back on the Web tab, click **Reload**, then open `https://YOUR_USERNAME.pythonanywhere.com`. Sign in as `hemanathanarish0@gmail.com` with the admin password you just configured.

The SQLite file is stored at `/home/YOUR_USERNAME/attendance.sqlite3`, outside the cloned repository. This is a free, limited hosting plan rather than a production guarantee; keep regular database backups. The deployment starts a fresh database and does not import your computer's local attendance history.

To update after pushing code to GitHub, use the Bash console:

```bash
cd ~/HTML-Workout
git pull
.venv/bin/pip install -r server/requirements.txt
```

Then click **Reload** on the PythonAnywhere Web tab. If the React UI changed, ensure the rebuilt `frontend/dist/` files are included in the GitHub commit before pulling.

## Paid alternative: Render

This repository also includes a Render Blueprint in `render.yaml` and a production [`Dockerfile`](./Dockerfile). It deploys the React build and Flask API together as one HTTPS web service, configures a persistent disk for SQLite, and generates a secret session key. **The persistent disk requires the paid Render Starter web-service plan.** Check the current price in Render before creating the service.

1. Push this project to a GitHub repository that your Render account can access.
2. Sign in to [Render](https://dashboard.render.com/) and choose **New → Blueprint**.
3. Connect the repository and select the branch you want to deploy.
4. Review the Blueprint. It creates the paid `starter` web service and a 1 GB persistent disk. Keep the persistent disk attached: without it, account and attendance data can be lost on redeploy.
5. When prompted for `ADMIN_PASSWORD`, enter a strong password of at least 10 characters. Do not put the password into `render.yaml` or commit it to Git.
6. Create the Blueprint and wait for the first deploy to finish. Open the `onrender.com` URL shown on the service page and sign in using `ADMIN_EMAIL` and the password you supplied.

The live URL is public; anyone can reach its sign-in and registration pages. Partner information and reports require authentication. Keep the admin password private. The existing local SQLite database is not automatically uploaded to Render; the hosted service starts with a fresh database and creates the configured admin account.
