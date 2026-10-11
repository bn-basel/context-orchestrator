"""Notifications: everything that leaves the building as an email or a text.

Rule of thumb: domain code calls `outbox.enqueue(...)` inside its own
transaction and never sends anything directly. The worker's `dispatch_outbox`
job picks rows up and hands them to email_sender / sms_sender. See ADR 0008.
"""
