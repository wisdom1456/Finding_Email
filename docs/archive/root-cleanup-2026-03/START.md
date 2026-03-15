# 🚀 START - Legal Document Analysis Portal

## ✅ Your Setup is Complete!

All database tables exist, configuration is ready, and both servers are running!

**Current Status:**
- ✅ Backend: Running on http://localhost:8000
- ✅ Frontend: Running on http://localhost:5173
- ✅ Database: Schema applied, all tables exist
- ✅ Tailwind CSS: Fixed and working (v4.1.17)

## 🎯 Quick Start (2 Steps)

### Step 1: Start Backend (Terminal 1)

```bash
cd /Users/BRFlorida/Projects/Work/Finding_Emails
./start_backend.sh
```

**Or manually:**
```bash
cd /Users/BRFlorida/Projects/Work/Finding_Emails/src
python3 -m uvicorn legal_portal.api.main:app --reload --port 8000
```

✅ **When you see:** `Application startup complete.`
✅ **Test it:** Open http://localhost:8000/docs

---

### Step 2: Start Frontend (Terminal 2 - New Window)

```bash
cd /Users/BRFlorida/Projects/Work/Finding_Emails
./start_frontend.sh
```

**Or manually:**
```bash
cd /Users/BRFlorida/Projects/Work/Finding_Emails/frontend
npm run dev
```

✅ **When you see:** `Local: http://localhost:5173/`
✅ **Open:** http://localhost:5173

---

## 🌐 Access Your Application

Once both servers are running:

| What | URL |
|------|-----|
| **🏠 Application** | http://localhost:5173 |
| **📚 API Docs** | http://localhost:8000/docs |
| **❤️ Health Check** | http://localhost:8000/health |

---

## 👤 First Time Setup

1. **Register**: http://localhost:5173/register
   - Create your account

2. **Login**: Should auto-redirect after registration

3. **Create a Case**:
   - Click "New Case"
   - Fill in client details
   - Click "Create Case"

4. **Upload Documents**:
   - Click on your case
   - Click "Upload Files"
   - Select PDF/DOCX files

5. **Analyze**:
   - Click "Start Analysis"
   - Wait for processing (2-5 minutes)
   - View results

---

## ⚠️ Troubleshooting

### Backend Issues

**"command not found: uvicorn"**
```bash
# Use python3 -m uvicorn instead:
cd /Users/BRFlorida/Projects/Work/Finding_Emails/src
python3 -m uvicorn legal_portal.api.main:app --reload --port 8000
```

**Port 8000 already in use:**
```bash
lsof -ti:8000 | xargs kill -9
./start_backend.sh
```

**Missing dependencies:**
```bash
cd /Users/BRFlorida/Projects/Work/Finding_Emails
pip install -r requirements.txt
```

### Frontend Issues

**"Internal Error" or 500 on login page:**
- This is often due to Tailwind CSS configuration issues.
- Try reinstalling dependencies:
  ```bash
  cd frontend
  rm -rf node_modules package-lock.json
  npm install
  npm run dev
  ```
- Ensure `@tailwindcss/postcss` is installed.

**Port 5173 already in use:**
```bash
lsof -ti:5173 | xargs kill -9
./start_frontend.sh
```

**Missing dependencies:**
```bash
cd /Users/BRFlorida/Projects/Work/Finding_Emails/frontend
npm install
```

---

## 🛑 Stop the Application

In each terminal, press: **Ctrl + C**

Or kill processes:
```bash
# Kill backend
lsof -ti:8000 | xargs kill -9

# Kill frontend
lsof -ti:5173 | xargs kill -9
```

---

## 📋 Verification Checklist

Before using the app, verify:

- [ ] Backend running (check http://localhost:8000/health)
- [ ] Frontend running (check http://localhost:5173)
- [ ] Can access login page
- [ ] Can register new user
- [ ] Can create a case
- [ ] Can upload documents

---

## 📚 More Documentation

- **READY_TO_USE.md** - Complete usage guide
- **LAUNCH_APP.md** - Detailed troubleshooting
- **REFACTOR_README.md** - Full architecture
- **IMPLEMENTATION_SUMMARY.md** - What was built

---

## 🎊 You're Ready!

Your Legal Document Analysis Portal is fully set up and ready to use.

**Next:** Open http://localhost:5173 and create your first case! 🚀

---

**Quick Commands:**
```bash
# Start both (in separate terminals)
./start_backend.sh    # Terminal 1
./start_frontend.sh   # Terminal 2

# Or manually
python3 -m uvicorn legal_portal.api.main:app --reload --port 8000  # Terminal 1
npm run dev --prefix frontend                                       # Terminal 2
```

