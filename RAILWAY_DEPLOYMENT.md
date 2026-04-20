# 🚂 Railway Deployment Guide for NyayaVoice

This guide will walk you through deploying NyayaVoice on Railway.app — the easiest way to deploy this application.

---

## ✅ Prerequisites

1. **GitHub Account** — to push your code
2. **Railway Account** — sign up free at [railway.app](https://railway.app)
3. **Vapi Account** (optional, for voice calls) — sign up at [vapi.ai](https://vapi.ai) and use code `vapixhackblr` for $30 free credits

---

## 📦 Step 1: Push Your Code to GitHub

If you haven't already, push the `Hackathon/` folder to a GitHub repository:

```bash
cd Hackathon
git init
git add .
git commit -m "Initial commit - NyayaVoice"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/nyayavoice.git
git push -u origin main
```

---

## 🚀 Step 2: Deploy on Railway

### Option A: Deploy via Railway CLI (Recommended)

1. **Install Railway CLI:**
   ```bash
   npm install -g @railway/cli
   ```

2. **Login to Railway:**
   ```bash
   railway login
   ```

3. **Initialize and Deploy:**
   ```bash
   cd Hackathon
   railway init
   railway up
   ```

4. **Set Environment Variables:**
   ```bash
   railway variables set VAPI_API_KEY=your_vapi_api_key_here
   railway variables set VAPI_PUBLIC_KEY=your_vapi_public_key_here
   railway variables set QDRANT_URL=:memory:
   railway variables set BACKEND_URL=$(railway domain)
   ```

5. **Generate a Domain:**
   ```bash
   railway domain
   ```
   This will give you a public URL like `https://nyayavoice-production.up.railway.app`

### Option B: Deploy via Railway Dashboard

1. **Go to [railway.app](https://railway.app) and click "New Project"**

2. **Select "Deploy from GitHub repo"**
   - Connect your GitHub account
   - Select your `nyayavoice` repository
   - Railway will auto-detect the `railpack.yaml` configuration

3. **Set Environment Variables:**
   - Go to your project → **Variables** tab
   - Add the following:
     ```
     VAPI_API_KEY=your_vapi_api_key_here
     VAPI_PUBLIC_KEY=your_vapi_public_key_here
     QDRANT_URL=:memory:
     BACKEND_URL=https://your-app-name.up.railway.app
     ```
   - **Important:** Update `BACKEND_URL` after you generate a domain (next step)

4. **Generate a Public Domain:**
   - Go to **Settings** → **Networking**
   - Click **Generate Domain**
   - Copy the generated URL (e.g., `https://nyayavoice-production.up.railway.app`)
   - Go back to **Variables** and update `BACKEND_URL` with this URL

5. **Deploy:**
   - Railway will automatically build and deploy your app
   - Check the **Deployments** tab for build logs

---

## 🔧 Step 3: Configure Vapi (Optional — for Voice Calls)

If you want voice call functionality:

1. **Sign up at [vapi.ai](https://vapi.ai)**
   - Use promo code `vapixhackblr` for $30 free credits

2. **Get Your API Keys:**
   - Go to **Dashboard** → **API Keys**
   - Copy your `VAPI_API_KEY` and `VAPI_PUBLIC_KEY`

3. **Update Railway Environment Variables:**
   ```bash
   railway variables set VAPI_API_KEY=your_actual_vapi_api_key
   railway variables set VAPI_PUBLIC_KEY=your_actual_vapi_public_key
   ```

4. **Configure Vapi Webhook:**
   - In Vapi Dashboard, set your webhook URL to:
     ```
     https://your-railway-domain.up.railway.app/vapi-webhook
     ```

---

## 🗄️ Step 4: Upgrade to Qdrant Cloud (Optional — for Persistent Storage)

By default, NyayaVoice uses **in-memory Qdrant** (`:memory:`), which means:
- ✅ No setup required
- ✅ Works immediately
- ❌ Data is lost on restart

To persist your legal knowledge base and user conversations:

1. **Sign up at [cloud.qdrant.io](https://cloud.qdrant.io)**
   - Free tier: 1GB storage

2. **Create a Cluster:**
   - Click **Create Cluster**
   - Choose **Free Tier**
   - Copy your **Cluster URL** and **API Key**

3. **Update Railway Environment Variables:**
   ```bash
   railway variables set QDRANT_URL=https://your-cluster-url.qdrant.io
   railway variables set QDRANT_API_KEY=your_qdrant_api_key
   ```

4. **Redeploy:**
   ```bash
   railway up
   ```

---

## ✅ Step 5: Verify Deployment

1. **Check Health Endpoint:**
   ```bash
   curl https://your-railway-domain.up.railway.app/health
   ```
   Should return: `{"status":"ok","service":"NyayaVoice API"}`

2. **Open the App:**
   - Visit `https://your-railway-domain.up.railway.app`
   - You should see the NyayaVoice landing page

3. **Test the API:**
   - Visit `https://your-railway-domain.up.railway.app/docs`
   - This opens the interactive API documentation (Swagger UI)

---

## 🐛 Troubleshooting

### Build Fails

**Check the build logs:**
```bash
railway logs
```

**Common issues:**
- Missing `requirements.txt` → Make sure it's in the `Hackathon/` folder
- Python version mismatch → Railway uses Python 3.11 by default (specified in `runtime.txt`)

### App Crashes on Startup

**Check runtime logs:**
```bash
railway logs --tail
```

**Common issues:**
- Missing environment variables → Verify all required variables are set
- Port binding issue → Railway automatically sets `PORT` environment variable
- Qdrant connection timeout → Use `:memory:` for testing

### Voice Calls Not Working

**Checklist:**
- ✅ `VAPI_API_KEY` and `VAPI_PUBLIC_KEY` are set correctly
- ✅ Vapi webhook URL is configured in Vapi Dashboard
- ✅ Webhook URL uses HTTPS (Railway provides this automatically)

### Documents Not Generating

**Check:**
- ✅ `BACKEND_URL` is set to your Railway domain (with `https://`)
- ✅ `/generated_docs` directory is writable (Railway handles this automatically)

---

## 📊 Monitoring & Logs

**View real-time logs:**
```bash
railway logs --tail
```

**View metrics:**
- Go to Railway Dashboard → **Metrics** tab
- Monitor CPU, Memory, and Network usage

---

## 💰 Cost Estimate

**Railway Free Tier:**
- $5 free credit per month
- Enough for ~500 hours of runtime
- Perfect for development and testing

**Qdrant Cloud Free Tier:**
- 1GB storage
- Unlimited requests
- Perfect for small-scale deployments

**Vapi Free Credits:**
- $30 with promo code `vapixhackblr`
- ~300-500 voice call minutes

---

## 🔄 Updating Your Deployment

**Push changes to GitHub:**
```bash
git add .
git commit -m "Update feature X"
git push
```

Railway will automatically detect the push and redeploy.

**Or use Railway CLI:**
```bash
railway up
```

---

## 🎉 Success!

Your NyayaVoice app is now live on Railway! 🚀

**Share your deployment:**
- Landing page: `https://your-railway-domain.up.railway.app`
- API docs: `https://your-railway-domain.up.railway.app/docs`

---

## 📚 Additional Resources

- [Railway Documentation](https://docs.railway.app)
- [Qdrant Cloud Docs](https://qdrant.tech/documentation/cloud/)
- [Vapi Documentation](https://docs.vapi.ai)
- [FastAPI Documentation](https://fastapi.tiangolo.com)

---

## 🆘 Need Help?

- Railway Community: [Discord](https://discord.gg/railway)
- Qdrant Community: [Discord](https://discord.gg/qdrant)
- Vapi Support: [Discord](https://discord.gg/vapi)

---

**Built with ❤️ for underserved communities in India**
