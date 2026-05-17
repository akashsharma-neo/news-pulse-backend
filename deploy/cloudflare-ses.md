# Cloudflare DNS + Amazon SES

Complete after EC2 has an **Elastic IP** and Caddy hostnames are chosen.

## Cloudflare

1. Add your domain to Cloudflare (nameservers at registrar).
2. **DNS** (proxied, orange cloud):
   - `www` → A record → Elastic IP
   - `api` → A record → Elastic IP
3. **SSL/TLS** → Overview → **Full (strict)**
4. **SSL/TLS** → Edge Certificates → enable **Always Use HTTPS**
5. Optional: restrict origin firewall to [Cloudflare IP ranges](https://www.cloudflare.com/ips/) on ports 80/443 only.

Set on the server `.env`:

```bash
CADDY_DOMAIN_WWW=www.yourdomain.com
CADDY_DOMAIN_API=api.yourdomain.com
CADDY_ACME_EMAIL=you@yourdomain.com
DJANGO_ALLOWED_HOSTS=api.yourdomain.com
CORS_ALLOWED_ORIGINS=https://www.yourdomain.com
BASE_URL=https://api.yourdomain.com
NEXT_PUBLIC_API_URL=https://api.yourdomain.com/api
```

Rebuild and push the **frontend** image whenever `NEXT_PUBLIC_API_URL` changes.

## Amazon SES

1. SES console → **Verified identities** → verify your domain (DNS records in Cloudflare).
2. Request production access if still in sandbox.
3. **SMTP settings** → create credentials.
4. Add to `.env`:

```bash
EMAIL_HOST=email-smtp.ap-south-1.amazonaws.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=<SMTP username>
EMAIL_HOST_PASSWORD=<SMTP password>
DEFAULT_FROM_EMAIL=news@yourdomain.com
```

## First deploy checklist

- [ ] `config/env/prod.example` values filled (secret key ≥ 50 chars, DB passwords)
- [ ] `prod.deploy.example` ECR URIs and domains set
- [ ] `./deploy/deploy.sh`
- [ ] `docker exec -it np-django python manage.py createsuperuser`
- [ ] Optional: [seed tabs/sources](../docs/seed-tabs-and-sources.md)
- [ ] `./deploy/smoke-test.sh`
