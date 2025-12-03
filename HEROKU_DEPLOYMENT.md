# EasyRFP - Heroku Deployment Guide

This guide walks you through deploying EasyRFP to Heroku.

## Prerequisites

- [Heroku CLI](https://devcenter.heroku.com/articles/heroku-cli) installed
- Heroku account
- Stripe account (for payments)
- SendGrid or other SMTP service (for emails)

## Step 1: Create Heroku App

```bash
# Create a new Heroku app
heroku create your-app-name

# Verify it was created
heroku apps:info
```

## Step 2: Add Buildpacks (CRITICAL)

EasyRFP uses Selenium for web scraping, which requires Chrome/Chromedriver. You **must** add these buildpacks:

```bash
# Add buildpacks in this specific order
heroku buildpacks:add --index 1 heroku/python
heroku buildpacks:add --index 2 https://github.com/heroku/heroku-buildpack-google-chrome
heroku buildpacks:add --index 3 https://github.com/heroku/heroku-buildpack-chromedriver

# Verify buildpacks
heroku buildpacks
```

Expected output:
```
1. heroku/python
2. https://github.com/heroku/heroku-buildpack-google-chrome
3. https://github.com/heroku/heroku-buildpack-chromedriver
```

## Step 3: Add Heroku Postgres

```bash
# Add PostgreSQL database (mini tier for testing, upgrade later)
heroku addons:create heroku-postgresql:essential-0

# Verify DATABASE_URL was set automatically
heroku config:get DATABASE_URL
```

## Step 4: Set Environment Variables

### Required Variables (App will fail without these)

```bash
# Security - Generate a strong secret key
heroku config:set SECRET_KEY="$(openssl rand -hex 32)"

# Deployment settings
heroku config:set ENV="production"
heroku config:set RUN_DDL_ON_START="false"
heroku config:set START_SCHEDULER_WEB="false"
heroku config:set PUBLIC_APP_HOST="your-app-name.herokuapp.com"

# Admin user (for initial login)
heroku config:set ADMIN_EMAIL="admin@yourdomain.com"
heroku config:set ADMIN_PASSWORD="secure-password-here"

# Stripe (get from https://dashboard.stripe.com/apikeys)
heroku config:set STRIPE_SECRET_KEY="sk_live_your-key-here"
heroku config:set STRIPE_PUBLISHABLE_KEY="pk_live_your-key-here"

# Stripe Price IDs (create products in Stripe dashboard first)
# Professional tier ($79/mo)
heroku config:set STRIPE_PRICE_PROFESSIONAL="price_your-professional-price-id"

# Team tier ($199/mo)
heroku config:set STRIPE_PRICE_ENTERPRISE="price_your-team-price-id"

# Optional: Starter tier (if you create one)
heroku config:set STRIPE_PRICE_STARTER="price_your-starter-price-id"

# Stripe webhook secret (from https://dashboard.stripe.com/webhooks)
heroku config:set STRIPE_WEBHOOK_SECRET="whsec_your-webhook-secret"

# Email (SendGrid example - get from https://app.sendgrid.com)
heroku config:set SMTP_HOST="smtp.sendgrid.net"
heroku config:set SMTP_PORT="587"
heroku config:set SMTP_FROM="noreply@easyrfp.ai"
heroku config:set SMTP_USERNAME="apikey"
heroku config:set SMTP_PASSWORD="SG.your-sendgrid-api-key"
```

### Optional Variables

```bash
# AI Features (Ollama won't work on Heroku - use OpenAI)
heroku config:set AI_ENABLED="true"
heroku config:set AI_PROVIDER="openai"
heroku config:set OPENAI_API_KEY="sk-your-openai-key"

# SMS Alerts via Twilio (https://www.twilio.com/console)
heroku config:set SMS_ENABLED="true"
heroku config:set TWILIO_ACCOUNT_SID="ACxxxxxxxxxxxxx"
heroku config:set TWILIO_AUTH_TOKEN="your-auth-token"
heroku config:set TWILIO_FROM_NUMBER="+15551234567"

# File Storage (S3 or Cloudflare R2)
heroku config:set DOCS_BUCKET="easyrfp-uploads"
heroku config:set AWS_ACCESS_KEY_ID="your-key-id"
heroku config:set AWS_SECRET_ACCESS_KEY="your-secret-key"
heroku config:set AWS_REGION="us-east-1"
# For Cloudflare R2:
# heroku config:set S3_ENDPOINT_URL="https://account-id.r2.cloudflarestorage.com"
```

## Step 5: Create Stripe Products & Prices

1. Go to https://dashboard.stripe.com/products
2. Create products:

### Professional Plan
- Name: "EasyRFP Professional"
- Price: $79/month (recurring)
- Copy the **Price ID** (starts with `price_`) and use for `STRIPE_PRICE_PROFESSIONAL`

### Team Plan
- Name: "EasyRFP Team"
- Price: $199/month (recurring)
- Copy the **Price ID** and use for `STRIPE_PRICE_ENTERPRISE`

## Step 6: Configure Stripe Webhooks

1. Go to https://dashboard.stripe.com/webhooks
2. Click "Add endpoint"
3. Endpoint URL: `https://your-app-name.herokuapp.com/stripe/webhook`
4. Select events to listen to:
   - `checkout.session.completed`
   - `invoice.paid`
   - `invoice.payment_succeeded`
5. Copy the **Signing secret** (starts with `whsec_`)
6. Set it: `heroku config:set STRIPE_WEBHOOK_SECRET="whsec_..."`

## Step 7: Update Procfile (Already Configured)

Your `Procfile` should contain:

```
web: gunicorn -k uvicorn.workers.UvicornWorker app.main:app --log-level info
worker: python -m app.core.scheduler
```

This is already set up in the repo.

## Step 8: Deploy to Heroku

```bash
# Add Heroku remote if not already added
heroku git:remote -a your-app-name

# Deploy
git push heroku claude/review-saas-product-018AGbRs5w4ht5XabfCacVmj:main

# Or if on main branch:
# git push heroku main
```

## Step 9: Scale Dynos

```bash
# Start web dyno
heroku ps:scale web=1

# Start worker dyno (for scrapers and email digests)
heroku ps:scale worker=1

# Verify dynos are running
heroku ps
```

## Step 10: Run Database Migrations

```bash
# Run initial migrations (if using Alembic)
heroku run alembic upgrade head

# Or connect to the database and verify tables were created
heroku pg:psql
```

## Step 11: Verify Deployment

```bash
# Check logs
heroku logs --tail

# Open the app
heroku open

# Test login with admin credentials
# Email: admin@yourdomain.com
# Password: [whatever you set in ADMIN_PASSWORD]
```

## Step 12: Configure Custom Domain (Optional)

```bash
# Add custom domain
heroku domains:add easyrfp.ai
heroku domains:add www.easyrfp.ai

# Follow instructions to configure DNS
heroku domains

# Update config
heroku config:set PUBLIC_APP_HOST="easyrfp.ai"
```

## Common Issues & Troubleshooting

### Issue: "Application Error" on startup

**Solution:** Check logs for missing environment variables
```bash
heroku logs --tail
```

### Issue: Scrapers failing with "Chrome not found"

**Solution:** Verify buildpacks are installed correctly
```bash
heroku buildpacks
# Should show python, chrome, and chromedriver
```

### Issue: Database connection errors

**Solution:** Verify DATABASE_URL is set
```bash
heroku config:get DATABASE_URL
# Should return postgresql:// URL
```

### Issue: Emails not sending

**Solution:** Check SMTP credentials and test with:
```bash
heroku run python -c "from app.core.mail import send_email; send_email('test@example.com', 'Test', '<p>Test</p>')"
```

### Issue: Stripe webhooks failing

**Solution:**
1. Check webhook secret matches: `heroku config:get STRIPE_WEBHOOK_SECRET`
2. Verify webhook URL in Stripe dashboard
3. Check logs: `heroku logs --tail | grep stripe`

## Performance Optimization

### Use More Powerful Dynos

```bash
# Upgrade web dyno
heroku ps:resize web=standard-1x

# Upgrade worker dyno
heroku ps:resize worker=standard-1x
```

### Database Connection Pooling

Add PgBouncer addon:
```bash
heroku addons:create pgbouncer
```

### Monitoring

Add logging addon:
```bash
heroku addons:create papertrail
heroku addons:open papertrail
```

## Security Checklist

- [ ] `RUN_DDL_ON_START` is set to `false`
- [ ] `SECRET_KEY` is randomly generated (not default)
- [ ] Stripe is in **live mode** (keys start with `sk_live_` and `pk_live_`)
- [ ] Stripe webhook secret is configured
- [ ] SMTP credentials are for production service (not Mailtrap)
- [ ] Admin password is strong (not "admin")
- [ ] `PUBLIC_APP_HOST` matches your actual domain
- [ ] SSL is enabled (automatic on Heroku)

## Cost Estimates

### Minimum (Testing)
- Dynos: $7/mo (Eco web) + $7/mo (Eco worker) = **$14/mo**
- Postgres: $5/mo (Mini) = **$5/mo**
- **Total: ~$19/mo**

### Production (Recommended)
- Dynos: $25/mo (Standard-1X web) + $25/mo (Standard-1X worker) = **$50/mo**
- Postgres: $50/mo (Standard-0) = **$50/mo**
- SendGrid: Free (up to 100 emails/day) or $15/mo (40k emails)
- **Total: ~$100-115/mo**

## Next Steps

1. **Monitor performance**: `heroku logs --tail`
2. **Set up error tracking**: Add Sentry (see below)
3. **Configure backups**: `heroku pg:backups:schedule --at '02:00 America/New_York' DATABASE_URL`
4. **Add monitoring**: `heroku addons:create newrelic`
5. **Test payment flow**: Create a test subscription
6. **Test scrapers**: Verify opportunities are being imported
7. **Test email digests**: Check digest emails are sent

## Adding Error Tracking (Recommended)

```bash
# Install Sentry
pip install sentry-sdk[fastapi]

# Add to app/main.py
import sentry_sdk
sentry_sdk.init(dsn="your-sentry-dsn", environment="production")

# Set config
heroku config:set SENTRY_DSN="your-sentry-dsn"
```

## Support

- Heroku Docs: https://devcenter.heroku.com/
- Stripe Docs: https://stripe.com/docs
- SendGrid Docs: https://docs.sendgrid.com/

---

**Last Updated:** 2025-12-03
**EasyRFP Version:** 1.0
