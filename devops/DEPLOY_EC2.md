# AWS EC2 Deployment Guide

This guide walks you through deploying **OpenSource Assist** to an Amazon EC2 instance using Docker Compose and automated scripts.

---

## 1. Prerequisites on AWS

1. **Launch an EC2 Instance:**
   - **AMI**: Ubuntu 22.04 LTS or 24.04 LTS (x86_64)
   - **Instance Type**: `t3.small` (2 vCPU, 2 GB RAM) or `t3.medium` (recommended for embeddings & vector search). If using `t2.micro` or `t3.micro`, the setup script automatically enables **4GB Swap** to prevent memory exhaustion.
   - **Storage**: At least 20 GB gp3.
   - **Key Pair**: Download your `.pem` key (e.g., `my-key.pem`).

2. **Configure Security Group Inbound Rules:**
   | Type | Port Range | Source | Description |
   |---|---|---|---|
   | SSH | `22` | My IP (or `0.0.0.0/0`) | Secure Shell Access |
   | HTTP | `80` | `0.0.0.0/0` | Web Application Traffic |
   | HTTPS | `443` | `0.0.0.0/0` | SSL/TLS Web Traffic (optional) |

---

## 2. One-Command Automated Deployment

### Option A: From Windows via PowerShell (One-Click)

Run the included deployment script directly from your local terminal:

```powershell
.\devops\deploy.ps1 -EC2Host "<YOUR_EC2_PUBLIC_IP>" -KeyPath "C:\path\to\your-key.pem"
```

*This script automatically connects over SSH, transfers the project files, sets permissions, and triggers the containerized deployment.*

---

### Option B: Directly on the EC2 Server (SSH)

1. **Connect to your EC2 instance:**
   ```bash
   ssh -i /path/to/your-key.pem ubuntu@<YOUR_EC2_PUBLIC_IP>
   ```

2. **Clone your repository & run setup:**
   ```bash
   # Clone the repo (or copy project folder)
   git clone <YOUR_GIT_REPO_URL> open-source-assist
   cd open-source-assist

   # Run the one-time EC2 server initialization (Installs Docker, Compose, Swap space)
   chmod +x devops/*.sh
   ./devops/ec2-setup.sh

   # Apply Docker group without logging out
   newgrp docker
   ```

3. **Configure Environment Variables:**
   ```bash
   cp .env.example .env
   nano .env
   ```
   *Make sure to set `JWT_SECRET_KEY`, `GEMINI_API_KEY`, `GITHUB_TOKEN`, and `FRONTEND_URL=http://<YOUR_EC2_PUBLIC_IP>`.*

4. **Deploy:**
   ```bash
   ./devops/deploy.sh
   ```

---

## 3. Option C: Automated CI/CD via GitHub Actions

To enable automatic continuous deployment whenever you push to GitHub:
1. Go to your GitHub Repository -> **Settings** -> **Secrets and variables** -> **Actions**.
2. Add the following repository secrets:
   - `EC2_HOST`: Your EC2 Public IP or DNS (e.g. `54.210.12.34`)
   - `EC2_USER`: `ubuntu`
   - `EC2_SSH_KEY`: The complete contents of your private `.pem` key file.
   - `EC2_APP_DIR`: `/home/ubuntu/open-source-assist` (optional, defaults to `/home/ubuntu/open-source-assist`)

Every push to `main` will now automatically test, build, and deploy to your EC2 instance!

---

## 4. Verifying & Managing the Deployment

- **Web Application**: `http://<YOUR_EC2_PUBLIC_IP>`
- **Interactive API Docs**: `http://<YOUR_EC2_PUBLIC_IP>/docs`
- **View Container Status**: `docker compose -f docker-compose.prod.yml ps`
- **View Live Backend Logs**: `docker compose -f docker-compose.prod.yml logs -f backend`
- **Restart Services**: `docker compose -f docker-compose.prod.yml restart`
