---
title: Docker build failure / image won't start
tags: docker, dockerfile, build failed, container, image, exit code
url: https://docs.docker.com/build/building/best-practices/
---
A Docker build failure happens during `docker build` (a command in the
Dockerfile itself failed, e.g. a missing file in COPY, a package install
error, or a wrong base image) and is distinct from a container that builds
fine but exits immediately after `docker run` (usually the app's entrypoint
crashed on startup — check `docker logs` for the actual application error,
not the Docker layer). Fix: read the build output for the exact failing
step line, confirm every path in COPY/ADD actually exists relative to the
build context, and pin dependency versions in the Dockerfile so a build
that worked yesterday doesn't silently break from an upstream update today.