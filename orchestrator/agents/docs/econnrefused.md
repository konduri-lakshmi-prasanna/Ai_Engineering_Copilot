---
title: ECONNREFUSED / address already in use
tags: ECONNREFUSED, port, connection refused, EADDRINUSE, network, database connection
url: https://nodejs.org/api/errors.html#common-system-errors
---
ECONNREFUSED means the app tried to connect to a host:port and nothing was
listening there — common when a backend tries to reach a database or another
service before that service has finished starting, when a connection string
points at "localhost" inside a container instead of the correct service
hostname, or when a firewall/security group blocks the port. EADDRINUSE is
the opposite problem: the app itself failed to start because another
process already owns that port. Fix for ECONNREFUSED: verify the host/port
in the connection string matches the actual deployed service name, and add
retry/backoff on startup so a slow-starting dependency doesn't crash the
app. Fix for EADDRINUSE: find and stop the process already using the port,
or configure the app to use a different port.