# 🚀 Launch Application

Your database is fully configured! Now let's start using the app.

## Quick Launch (Copy & Paste)

### Terminal 1: Start Backend
```bash
cd /Users/BRFlorida/Projects/Work/Finding_Emails/src
uvicorn legal_portal.api.main:app --reload --port 8000
```

### Terminal 2: Start Frontend (open new terminal)
```bash
cd /Users/BRFlorida/Projects/Work/Finding_Emails/frontend
npm run dev
```

## Access Points

Once both are running:

- **Application**: http://localhost:5173
- **API Documentation**: http://localhost:8000/docs
- **API Health Check**: http://localhost:8000/health

## First Time Setup

1. **Register**: http://localhost:5173/register
   - Create your account with email/password
   
2. **Login**: http://localhost:5173/login
   - Should auto-redirect after registration

3. **Dashboard**: http://localhost:5173/app
   - See your cases overview

## Test the Full Workflow

### 1. Create a Case
- Click "New Case" button
- Fill in:
  - Client Name: e.g., "John Doe"
  - Reference Number: e.g., "CASE-2024-001" (optional)
  - Description: e.g., "Landlord-tenant dispute" (optional)
- Click "Create Case"

### 2. Upload Documents
- Click on your new case from the list
- Click "Upload Files" button
- Select PDF documents (or DOCX, images)
- Wait for upload to complete (green checkmarks)

### 3. Start Analysis
- Click "Start Analysis" button
- Status will change: pending → processing → completed
- This may take a few minutes depending on document size
- The page polls automatically for updates

### 4. View Results
- Once status shows "completed"
- Click "View Results" button
- See the AI-generated findings email
- Download PDF/DOCX (if implemented)

## Monitoring

### Backend Logs (Terminal 1)
Watch for:
- API requests coming in
- Document processing progress
- Any errors or warnings

### Frontend Console (Browser DevTools)
- Press F12 or right-click → Inspect
- Check Console tab for JavaScript errors
- Check Network tab for API calls

### Supabase Dashboard
https://app.supabase.com
- Monitor database tables (Table Editor)
- Check storage uploads (Storage)
- View authentication users (Authentication)
- Check logs for errors (Logs & Insights)

## Common Issues & Solutions

### Backend Issues

**Port already in use:**
```bash
# Find process using port 8000
lsof -ti:8000 | xargs kill -9

# Then restart backend
cd /Users/BRFlorida/Projects/Work/Finding_Emails/src
uvicorn legal_portal.api.main:app --reload --port 8000
```

**Import errors:**
```bash
# Make sure you're in the src directory
cd /Users/BRFlorida/Projects/Work/Finding_Emails/src

# Check Python path includes src
pwd  # Should show: .../Finding_Emails/src
```

**Missing OpenAI key:**
```bash
# Check your .env file has OPENAI_API_KEY
cat /Users/BRFlorida/Projects/Work/Finding_Emails/.env | grep OPENAI
```

### Frontend Issues

**Port 5173 already in use:**
```bash
# Kill existing process
lsof -ti:5173 | xargs kill -9

# Restart frontend
cd /Users/BRFlorida/Projects/Work/Finding_Emails/frontend
npm run dev
```

**Build errors:**
```bash
# Clear SvelteKit cache and rebuild
cd /Users/BRFlorida/Projects/Work/Finding_Emails/frontend
rm -rf .svelte-kit
npm run dev
```

**"Cannot find module" errors:**
```bash
# Reinstall dependencies
cd /Users/BRFlorida/Projects/Work/Finding_Emails/frontend
rm -rf node_modules package-lock.json
npm install
npm run dev
```

### Authentication Issues

**Can't login/register:**
- Check browser console for errors
- Verify Supabase URL and keys in frontend/.env
- Check that auth is enabled in Supabase Dashboard → Authentication

**"Invalid JWT":**
- Keys might be mismatched between .env files
- Regenerate keys in Supabase Dashboard if needed

### Upload Issues

**Files won't upload:**
- Check that `documents` storage bucket exists
- Verify storage policies are applied
- Check file size (default limit is 50MB)
- Check browser Network tab for 403/404 errors

**"Permission denied":**
- Storage policies might not be correct
- Re-run the storage policy SQL from SETUP_INSTRUCTIONS.md

### Analysis Issues

**Analysis gets stuck on "processing":**
- Check backend logs for errors
- Verify OPENAI_API_KEY is valid
- Check OpenAI usage/limits: https://platform.openai.com/usage
- Look at analysis_results table in Supabase for error messages

**"No documents found":**
- Make sure documents uploaded successfully
- Check documents table in Supabase
- Verify storage_path is set correctly

## Stopping the Application

### Graceful Shutdown
In each terminal, press: `Ctrl + C`

### Force Stop (if needed)
```bash
# Kill backend
lsof -ti:8000 | xargs kill -9

# Kill frontend
lsof -ti:5173 | xargs kill -9
```

## Production Deployment

When you're ready to deploy:

1. **Backend** → Vercel, Railway, or Fly.io
2. **Frontend** → Vercel or Netlify
3. **Database** → Already on Supabase (production-ready)

See `REFACTOR_README.md` for deployment instructions.

## Development Tips

### Hot Reload
Both backend and frontend support hot reload:
- **Backend**: Changes to Python files auto-reload
- **Frontend**: Changes to Svelte files auto-rebuild

### API Testing
Use the interactive API docs:
```
http://localhost:8000/docs
```
- Try out endpoints directly
- See request/response formats
- Test with your JWT token

### Database Inspection
Use Supabase Table Editor:
- View all data in real-time
- Manually edit records for testing
- Run SQL queries

### Debugging
```bash
# Backend: Add print statements or use debugger
# They'll show in Terminal 1

# Frontend: Use browser DevTools
# Console.log statements appear in browser console
```

## Next Steps

Once everything is working:

1. ✅ Test with real legal documents
2. ✅ Customize AI prompts in `src/legal_portal/prompts/`
3. ✅ Adjust OpenAI settings in `.env`
4. ✅ Add more users via registration
5. ✅ Review cost tracking in dashboard
6. ✅ Plan production deployment

---

**You're all set!** 🎉

Open two terminals, run the commands above, and start analyzing legal documents!

