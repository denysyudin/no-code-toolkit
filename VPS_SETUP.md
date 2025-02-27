# No-Code Architects Toolkit: VPS Deployment Guide

This guide walks you through deploying the No-Code Architects Toolkit on your own VPS (Virtual Private Server) without cloud storage dependencies.

## Prerequisites

- A VPS with Ubuntu/Debian (recommended) or other Linux distribution
- Python 3.8 or higher installed
- `pip` and `venv` installed
- Nginx (recommended for production)
- A domain name (optional but recommended)

## Step 1: Clone the Repository

```bash
git clone https://github.com/your-username/no-code-architects-toolkit.git
cd no-code-architects-toolkit
```

## Step 2: Set Up Python Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Step 3: Generate API Key

Generate a secure API key:

```bash
openssl rand -base64 32
```

Save this API key, you'll need it in the next step.

## Step 4: Configure Local Storage

Run the provided script to set up local storage:

```bash
export API_KEY="your_generated_api_key"
chmod +x disable-cloud.sh
./disable-cloud.sh /var/www/storage http://your-domain.com
```

The script will:
- Create storage directories
- Set appropriate permissions
- Configure environment variables
- Save settings to a `.env` file

## Step 5: Verify Configuration

Make sure your environment variables are set correctly:

```bash
source ~/.bashrc
echo $API_KEY
echo $LOCAL_STORAGE_PATH
echo $BASE_URL
```

## Step 6: Test the Application

Run the application to verify it works:

```bash
gunicorn app:create_app() --bind 0.0.0.0:5000
```

Visit `http://your-server-ip:5000` to check if the server is running. 

## Step 7: Set Up Nginx (Recommended for Production)

Install Nginx:

```bash
sudo apt update
sudo apt install nginx
```

Create a Nginx configuration file:

```bash
sudo nano /etc/nginx/sites-available/nca-toolkit
```

Add the following configuration:

```nginx
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;

    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location /storage/ {
        alias /var/www/storage/;
        autoindex off;
    }
}
```

Enable the site and restart Nginx:

```bash
sudo ln -s /etc/nginx/sites-available/nca-toolkit /etc/nginx/sites-enabled/
sudo nginx -t  # Test the configuration
sudo systemctl restart nginx
```

## Step 8: Set Up SSL with Let's Encrypt (Recommended)

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com -d www.your-domain.com
```

## Step 9: Run as a Systemd Service

Create a service file:

```bash
sudo nano /etc/systemd/system/nca-toolkit.service
```

Add the following configuration:

```ini
[Unit]
Description=No-Code Architects Toolkit
After=network.target

[Service]
User=your-username
WorkingDirectory=/path/to/no-code-architects-toolkit
Environment="PATH=/path/to/no-code-architects-toolkit/venv/bin"
EnvironmentFile=/path/to/no-code-architects-toolkit/.env
ExecStart=/path/to/no-code-architects-toolkit/venv/bin/gunicorn app:create_app() --bind 0.0.0.0:5000 --workers 4

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable nca-toolkit
sudo systemctl start nca-toolkit
sudo systemctl status nca-toolkit
```

## Troubleshooting

### Storage Directory Permissions

If you encounter permission issues with the storage directory:

```bash
sudo chown -R your-username:your-username /var/www/storage
sudo chmod -R 755 /var/www/storage
```

### Application Logs

Check the application logs:

```bash
sudo journalctl -u nca-toolkit
```

### Service Won't Start

Verify your environment settings:

```bash
cat .env
```

Ensure all required environment variables are set:
- API_KEY
- LOCAL_STORAGE_PATH
- BASE_URL

## Maintenance

### Regular Backups

Set up a cron job to back up the storage directory:

```bash
sudo crontab -e
# Add this line for daily backups at 2 AM
0 2 * * * tar -czf /var/backups/nca-storage-$(date +\%Y\%m\%d).tar.gz /var/www/storage
```

### Storage Cleanup

To prevent your disk from filling up, set up a cleanup script:

```bash
sudo nano /usr/local/bin/cleanup-storage.sh
```

Add this content:

```bash
#!/bin/bash
# Delete files older than 30 days
find /var/www/storage -type f -mtime +30 -delete
```

Make it executable and set up a cron job:

```bash
sudo chmod +x /usr/local/bin/cleanup-storage.sh
sudo crontab -e
# Add this line to run weekly
0 0 * * 0 /usr/local/bin/cleanup-storage.sh
``` 