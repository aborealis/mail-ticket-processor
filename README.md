# Mail Ticket Processor

Do you use your email inbox to manage customer support or client communications?
Would you like every conversation to automatically get a **ticket number**, while still keeping everything inside your familiar inbox?

**Mail Ticket Processor** is a lightweight Python script that turns your regular email inbox into a basic ticketing system — without the need to switch platforms or use external tools.

## ✅ What It Does

- Automatically assigns a **ticket number** (based on the IMAP UID assigned to the message) to every new email that starts a new conversation by replacing original message with a modified copy with `Ticket XXX: <original subject>` subject line. All the original messages are moved to a separate folder (`Originals`) to keep your inbox clean.
- Sends your custom **auto-reply** to the sender confirming receipt and including the ticket number. Only works for new conversations.
- Skips assigning ticket numbers and auto-replies for specific no-reply senders.


## 📦 Requirements

- Python 3.8+
- IMAP mailbox with IDLE support (Zoho, Gmail, etc.)
- Python `imapclient` library
- A folder on your IMAP server to store original messages that start new conversations (defaults to `Originals`)

## 🔐 Configuration

In `app.py`:

- Set the values for `IMAP_HOST`, `SMTP_HOST`, `SMTP_PORT`, `USERNAME`, `PASSWORD`, as well as `MAILBOX` and `ORIG_MAIL_DIR` according to your email provider.
- Set `EXCLUDED_SENDERS` — usually includes no-reply addresses.
- Customize the `TICKET_REPLY_TEMPLATE` as needed.


## 🚀 Deployment on a Linux Server

### 1. Install Prerequisites

The commands below are for Ubuntu/Debian-based systems.

Install a virtual (isolated) environment to run the script:

```bash
sudo apt install python3 python3-pip python3-venv -y
sudo apt install pipx
pipx install pipenv
```

### 2. Prepare the Environment

```bash
mkdir ~/mail-ticket
cd ~/mail-ticket
pipenv install imapclient
```

Copy the script `app.py` into this directory and adjust the variables as described above.

Now enter the virtual environment and run the script:

```bash
pipenv shell
python app.py
```

Test if everything works. If satisfied with the result, stop the script and exit the environment:

```bash
exit
```

### 3. Create a Daemon From This Script

Get the path to the Python interpreter inside your virtual environment:

```bash
cd ~/mail-ticket
pipenv shell
which python  # Note this path for the systemd unit
exit
```

Create the file `/etc/systemd/system/mail-ticket.service`:

```ini
[Unit]
Description=Mail Ticket Processor Service
After=network.target

[Service]
User=YOUR_USERNAME
WorkingDirectory=/path_to_home_dir/mail-ticket
ExecStart=/path_to_python /path_to_home_dir/mail-ticket/app.py
Restart=on-failure
RestartSec=10s

[Install]
WantedBy=multi-user.target
```

> Replace `/path_to_python` with the actual interpreter path you found above, and `/path_to_home_dir` with the full path to your home directory (usually `/home/YOUR_USERNAME`).


### 4. Starting the Service

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now mail-ticket.service
sudo systemctl status mail-ticket.service # Check if it is enabled and running
```

To restart the service (if you made changes in code), simply run `sudo systemctl restart mail-ticket.service`

### 5. Live Logs

```bash
sudo journalctl -u mail-ticket.service -f
```

## ❌ Uninstalling

To completely uninstall the script, run the following:

```bash
sudo systemctl disable --now mail-ticket.service
sudo rm /etc/systemd/system/mail-ticket.service
sudo systemctl daemon-reload

cd ~/mail-ticket
pipenv --rm
cd
rm -r ~/mail-ticket
```
