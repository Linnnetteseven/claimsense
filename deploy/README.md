# Deploy the Hakiki API on an Oracle Cloud VM

This deployment runs only the FastAPI backend. The React frontend stays on Vercel. Oracle Autonomous Database remains the shared application store. The included Docker image contains backend source and Python packages only; it excludes the wallet and environment files.

## 1. Prepare an Ubuntu VM

Create an Ubuntu VM in OCI and reserve a public IP. In the VCN security list or network security group, add inbound TCP rules for ports **80** and **443** from the audience you intend to serve (use a restricted source CIDR for a private demo). On the VM, allow those ports in the instance firewall:

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

Install Docker Engine and the Docker Compose plugin using Docker's official Ubuntu instructions. Install Nginx and Certbot from Ubuntu packages. Keep backend port **8001** closed to the public; Compose binds it to loopback for Nginx.

## 2. Put the code and environment file in place

After the reviewed branch has been merged or otherwise made available to the deployment account, clone that repository revision and create a private environment file from the example:

```bash
sudo mkdir -p /opt/hakiki
sudo chown "$USER":"$USER" /opt/hakiki
git clone https://github.com/Linnnetteseven/claimsense.git /opt/hakiki
cd /opt/hakiki
cp .env.example .env
chmod 600 .env
```

Set the Vercel production URL in `.env`. For example:

```dotenv
DB_BACKEND=oracle
ORACLE_USER=HAKIKI_APP
ORACLE_PASSWORD=replace-with-secret
ORACLE_DSN=your_adb_service_alias
ORACLE_WALLET_DIR=/run/secrets/oracle-wallet
ORACLE_WALLET_PASSWORD=replace-with-wallet-password
ALLOWED_ORIGINS=https://your-hakiki-project.vercel.app
DEPLOYED_FRONTEND_URL=https://your-hakiki-project.vercel.app
```

Use the exact service alias/connection string from the Autonomous Database connection details. The API does not expose database credentials. If using walletless TLS, leave `ORACLE_WALLET_DIR` empty and remove the wallet bind mount from `deploy/docker-compose.yml` before starting the container.

## 3. Copy the wallet securely (mTLS deployments only)

Create `/opt/hakiki/oracle-wallet` with owner-only permissions. Copy the unzipped wallet to that directory over an encrypted channel such as `scp`; keep it outside the Git repository and never add it to the Docker image. Restrict permissions, for example `chmod 700 oracle-wallet` and `chmod 600 oracle-wallet/*`. Compose mounts this folder read-only at `/run/secrets/oracle-wallet`.

Do not include wallet files, `.env`, passwords, private keys, or API secrets in commits, CI logs, screenshots, or image layers. Rotate any credential that has been exposed.

## 4. Apply Oracle SQL and start the backend

Connect to Autonomous Database as `HAKIKI_APP` and apply the application schema (`backend/db/schema.sql`) if it has not been applied. Then apply `backend/db/views.sql` as the same schema user to enable Management Overview. The SQL scripts create the database objects; they do not seed data automatically. For an all-synthetic demo dataset, follow the seeder instructions in the root README after verifying the target database is a demo database.

Start the backend:

```bash
docker compose --env-file .env -f deploy/docker-compose.yml up -d --build
docker compose --env-file .env -f deploy/docker-compose.yml logs -f backend
```

For demo analytics, run the synthetic seeder once from an environment configured with the same Oracle variables, as described in the root README. Do not put real patient information in the demo database.

## 5. Configure HTTPS and CORS

Point your DNS A record at the VM public IP. Configure Certbot to issue a certificate for that hostname. Copy `deploy/nginx-hakiki.conf` to `/etc/nginx/sites-available/hakiki`, replace `hakiki.example.org`, enable the site, and run `sudo nginx -t && sudo systemctl reload nginx`.

`ALLOWED_ORIGINS` must contain the exact Vercel origin (scheme and host, no path). Keep `DEPLOYED_FRONTEND_URL` set to that same origin so the application adds it to CORS. Never use `*` for the production allowlist.

## 6. Check service health

From the VM, check the backend through Nginx and verify the Oracle connection:

```bash
curl -fsS https://hakiki.example.org/health/db
```

Expect `active_backend: oracle`, `connected: true`, and the configured connection mode. The response contains no credentials. Check `docker compose ... logs backend` if health reports false.

## systemd alternative (without Docker)

The file `deploy/hakiki-backend.service` is an alternative. Install the repository at `/opt/hakiki`, create a Python virtual environment at `/opt/hakiki/venv`, install `backend/requirements.txt`, and put environment variables in `/etc/hakiki/hakiki.env` with mode `600`. Keep wallet files outside the repository and set `ORACLE_WALLET_DIR` to their private directory. Install the unit at `/etc/systemd/system/hakiki-backend.service`, then run `sudo systemctl daemon-reload && sudo systemctl enable --now hakiki-backend`.

Nginx should still proxy to the loopback backend. Do not expose port 8001 publicly. Cloud resources, DNS, certificates, Oracle users, firewall rules, and secrets must be configured by the operator; this repository does not run cloud commands.
