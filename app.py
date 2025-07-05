"""
This script assigns ticket numbers to incoming emails. How it works:

1. If it's a new email, that starts a new conversation:
    - The copy of the original email is saved the same inbox folder
      with a modified subject line: "Ticket XXX: <Original subject>",
      where XXX is the UID of the original email on the IMAP server.
    - The original email is marked as read and moved to the "Originals"
      folder (you need to have one on your IMAP server).
    - The sender receives an auto-reply with the ticket number.

2. If the email is a reply within an existing conversation, or is from
   an excluded sender, it is ignored.

Uses IMAP IDLE to listen for incoming messages.
Dependencies: imapclient (pipenv install imapclient)
"""

import time
import re
import email
import traceback
import socket
import ssl
import smtplib
from typing import Union
from email.message import EmailMessage
from email.header import decode_header, make_header
from email.utils import make_msgid, parseaddr, formataddr
from imapclient import IMAPClient
from imapclient.exceptions import IMAPClientError

# Example configuration (replace with your actual credentials and server info)
IMAP_HOST = 'imap.example.com'
SMTP_HOST = 'smtp.example.com'
SMTP_PORT = 465
USERNAME = 'user@example.com'
PASSWORD = 'your_password'
MAILBOX = 'INBOX'
ORIG_MAIL_DIR = 'Originals'

# List the recipients for whom you do not want to generate ticket numbers
EXCLUDED_SENDERS = {
    "user@example.com",
    "noreply@example1.com",
    "noreply@example2.com",
}

# Set your autoreply here. The {ticket_uid} will be replaced to the actual ticket number.
TICKET_REPLY_TEMPLATE = (
    "Thank you for your message! We have received it. You will get a response within 24 hours.\n\n"
    "Your ticket number: {ticket_uid}"
)

# Do not change the code below this line
# pylint: disable=too-many-locals


def clean_header_value(value: str) -> str:
    """
    Remove line breaks and control characters from a header value.
    """

    return re.sub(r'[\r\n]+', ' ', value).strip()


def send_ticket_confirmation(recipient: str,
                             ticket_uid: int,
                             original_subject: Union[str, None],
                             original_message_id: Union[str, None]
                             ) -> None:
    """
    Sends an auto-reply with the assigned ticket number as a response to the original message.

    :param recipient: Email address of the sender
    :param ticket_uid: UID of the original message in the inbox folder (set by the IMAP server)
    :param original_subject: Subject of the original message
    :param original_message_id: Message-ID of the original email
    """

    subject = f"Ticket {ticket_uid}: {original_subject or '(No subject)'}"
    body = TICKET_REPLY_TEMPLATE.format(ticket_uid=ticket_uid)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = USERNAME
    msg["To"] = recipient

    if original_message_id:
        msg["In-Reply-To"] = original_message_id
        msg["References"] = original_message_id

    msg.set_content(body)

    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.login(USERNAME, PASSWORD)
        smtp.send_message(msg)

    print(
        f"↰ Auto-reply with ticket number {ticket_uid} sent to {recipient}",
        flush=True
    )


def save_ticket_copy(client: IMAPClient, original_msg: EmailMessage, uid: int) -> str:
    """
    Creates a new email with modified subject and stores it in the INBOX.
    Returns the Message-ID of the original message.
    """

    subject = clean_header_value(original_msg.get("Subject", "(No subject)"))
    name, email_addr = parseaddr(original_msg.get("From", ""))
    message_id = make_msgid()

    # Headers
    new_msg = EmailMessage()
    new_msg["Subject"] = f"Ticket {uid}: {subject}"
    new_msg["From"] = formataddr((name or "Unknown Sender", email_addr))
    new_msg["To"] = USERNAME
    new_msg["Message-ID"] = message_id
    new_msg["Reply-To"] = email_addr
    new_msg["X-Original-Sender"] = email_addr

    # Body & attachments
    plain_parts = []
    html_parts = []
    attachments = []
    inline_images = []

    for part in original_msg.walk() if original_msg.is_multipart() else [original_msg]:
        ctype = part.get_content_type()
        disp = str(part.get("Content-Disposition", "")).lower()
        charset = part.get_content_charset() or "utf-8"

        if ctype.startswith("image/") and part.get("Content-ID"):
            inline_images.append((
                part.get("Content-ID").strip("<>"),
                part.get_payload(decode=True),
                *ctype.split("/", 1)
            ))

        elif "attachment" in disp:
            attachments.append((
                part.get_payload(decode=True),
                *ctype.split("/", 1),
                part.get_filename()
            ))

        elif ctype == "text/plain":
            plain_parts.append(
                part.get_payload(decode=True).decode(charset, errors="replace")
            )

        elif ctype == "text/html":
            html_parts.append(
                part.get_payload(decode=True).decode(charset, errors="replace")
            )

    if html_parts:
        related = EmailMessage()
        related.set_content("\n\n".join(html_parts), subtype="html")

        for cid, payload, maintype, subtype in inline_images:
            related.add_related(
                payload, maintype=maintype, subtype=subtype, cid=cid
            )

        alt = EmailMessage()
        alt.set_content(
            "\n\n".join(plain_parts)
            or "(no plain text)", subtype="plain"
        )
        alt.add_alternative(related)

        new_msg.make_mixed()
        new_msg.attach(alt)

    elif plain_parts:
        new_msg.set_content("\n\n".join(plain_parts))

    else:
        new_msg.set_content("(No text)")

    for payload, maintype, subtype, filename in attachments:
        new_msg.add_attachment(
            payload, maintype=maintype, subtype=subtype, filename=filename
        )

    # Save to INBOX
    client.append(MAILBOX, new_msg.as_bytes())
    print(
        f"⭳ Saved new message Ticket {uid}: {subject} to INBOX",
        flush=True
    )

    return message_id


def process_new_messages(client: IMAPClient) -> None:
    """
    Processes new unseen emails. If it's a new ticket, sends confirmation
    and creates a copy with a ticket number.
    """

    messages = client.search(['UNSEEN'])

    for uid in messages:
        raw_message = client.fetch([uid], ['RFC822'])[uid][b'RFC822']
        msg = email.message_from_bytes(raw_message)

        raw_subject = msg.get("Subject")
        decoded_subject = str(
            make_header(decode_header(raw_subject or "(No subject)"))
        )

        print("⚑ New message:", decoded_subject, flush=True)

        from_header = msg.get("From", "")
        _, sender_email = parseaddr(from_header)
        sender_email = sender_email.lower()

        if sender_email.lower() in EXCLUDED_SENDERS:
            print(
                f"⏭ Sender {sender_email} is excluded — skipping.",
                flush=True
            )
            continue

        # If "Ticket" is in the subject line
        if decoded_subject.strip().lower().startswith("ticket"):
            print(
                "⏭ Message already contains a ticket number — skipping.",
                flush=True
            )
            continue

        # If this is the reply to the existing conversation
        in_reply_to = msg.get("In-Reply-To")
        references = msg.get("References")

        if in_reply_to or references:
            print(
                "⏭ Message is a reply — skipping.",
                flush=True
            )
            continue

        original_message_id = save_ticket_copy(client, msg, uid)
        send_ticket_confirmation(
            recipient=msg.get("From"),
            ticket_uid=uid,
            original_subject=decoded_subject,
            original_message_id=original_message_id
        )
        client.add_flags(uid, [b'\\Seen'])
        client.move([uid], ORIG_MAIL_DIR)


def connect_to_mailbox():
    """
    Establishes and returns a logged-in IMAP client.
    """

    client = IMAPClient(IMAP_HOST)
    client.login(USERNAME, PASSWORD)
    client.select_folder(MAILBOX)
    print(f"🗲 Connected to {MAILBOX}, waiting for new mail...", flush=True)
    return client


def handle_idle(client: IMAPClient):
    """
    Performs one idle-check cycle and returns responses.
    """

    try:
        client.idle()
        responses = client.idle_check(timeout=60)

    finally:
        try:
            client.idle_done()

        except (IMAPClientError, socket.error, ssl.SSLError):
            pass

    return responses


def monitor_mailbox():
    """
    Main mailbox monitoring loop.
    """

    with connect_to_mailbox() as client:
        while True:
            responses = handle_idle(client)

            if responses:
                print("⚐ Changes detected, checking new messages...", flush=True)
                process_new_messages(client)


def idle_loop():
    """
    Main loop for monitoring the IMAP inbox using IDLE.
    Automatically reconnects on failure.
    """

    while True:
        try:
            monitor_mailbox()
        except (IMAPClientError, socket.error, ssl.SSLError) as e:
            print(f"🞩 Connection or execution error:\n {e}", flush=True)
            print(traceback.format_exc())
            print("↺ Reconnecting in 10 seconds...", flush=True)
            time.sleep(10)


if __name__ == "__main__":
    idle_loop()
