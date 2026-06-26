# Deployment Plan: Nextleap Zomato

This document outlines the steps required to deploy the Nextleap Zomato application, with the **Backend hosted on Railway** and the **Frontend hosted on Vercel**.

## 1. Backend Deployment (Railway)

The backend is a FastAPI Python application. Railway can easily host it using its native Nixpacks builder which will automatically detect your `requirements.txt` and install dependencies.

### Prerequisites
- Create a [Railway](https://railway.app/) account.
- Push your project to a GitHub repository.

### Steps
1. **Create a New Project**:
   - Go to the Railway dashboard and click **New Project**.
   - Select **Deploy from GitHub repo** and choose your `Nextleap Zomato` repository.

2. **Configure Environment Variables**:
   - Once the service is created, go to the **Variables** tab.
   - Add your Groq API key: `GROQ_API_KEY=your_actual_api_key_here`.
   - (Railway will automatically inject a `PORT` variable, which FastAPI/Uvicorn uses).

3. **Start Command (Recommended)**:
   - Railway will typically auto-detect FastAPI. However, to ensure it runs correctly, go to the **Settings** tab of your service.
   - Scroll down to the **Start Command** field and enter:
     ```bash
     uvicorn src.main:app --host 0.0.0.0 --port $PORT
     ```

4. **Generate a Public Domain**:
   - In the **Settings** tab under **Networking**, click **Generate Domain** to get a public HTTPS URL (e.g., `https://your-backend-app.up.railway.app`).
   - *Save this URL! You will need it for the frontend configuration.*

5. **Verify CORS**:
   - The backend already has CORS configured to allow all origins (`allow_origins=["*"]`) in `src/main.py` (lines 107-113). This ensures your Vercel frontend can communicate with the backend securely.

---

## 2. Frontend Configuration Updates

Currently, the frontend in `static/app.js` makes API calls to relative paths like `fetch('/metadata/locations')`. Since the frontend and backend will now be hosted on separate domains, you must update the frontend to point to the new Railway backend URL.

### Code Updates Needed
1. Open `static/app.js`.
2. Define your new backend URL at the top of the file:
   ```javascript
   const API_BASE_URL = 'https://your-backend-app.up.railway.app'; // Replace with your actual Railway Domain
   ```
3. Update all `fetch()` calls in the file. Change paths like:
   - `fetch('/metadata/locations')` ➡️ `fetch(`${API_BASE_URL}/metadata/locations`)`
   - `fetch('/metadata/cuisines')` ➡️ `fetch(`${API_BASE_URL}/metadata/cuisines`)`
   - `fetch('/recommend', ...)` ➡️ `fetch(`${API_BASE_URL}/recommend`, ...)`

4. Commit and push these changes to GitHub before deploying to Vercel.

---

## 3. Frontend Deployment (Vercel)

The frontend consists of vanilla HTML, CSS, and JS located in the `static/` directory.

### Prerequisites
- Create a [Vercel](https://vercel.com/) account.

### Steps
1. **Create a New Project**:
   - Go to your Vercel dashboard and click **Add New...** > **Project**.
   - Import your `Nextleap Zomato` GitHub repository.

2. **Configure the Project Root Directory**:
   - In the "Configure Project" screen, look for the **Root Directory** setting.
   - Click **Edit** and select the `static` folder. (This tells Vercel that your frontend files are located inside `static/`).

3. **Deploy**:
   - Leave the Framework Preset as "Other" and the Build Command empty (since it's a static site).
   - Click **Deploy**.

4. **Verify**:
   - Once deployed, Vercel will provide a public URL. Visit the URL to ensure the UI loads properly and successfully fetches the locations/cuisines from your Railway backend!
