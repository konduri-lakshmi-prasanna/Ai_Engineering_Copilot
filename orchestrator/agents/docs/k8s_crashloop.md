# Kubernetes CrashLoopBackOff

## Problem
A pod enters `CrashLoopBackOff` when its main container exits repeatedly. Kubernetes keeps restarting it with exponential back-off (10s, 20s, 40s … up to 5 minutes).

## Common Causes
1. **Application crash on startup** — unhandled exception, missing env variable, port already in use.
2. **Bad entrypoint / CMD** — binary not found, wrong path, missing execute permission.
3. **Missing config / secret** — `ConfigMap` or `Secret` not mounted, env var not injected.
4. **OOMKilled before livenessProbe passes** — process exceeds memory limit immediately.
5. **Dependency not ready** — app fails on DB/Redis connection at boot before they are ready.

## Diagnosis Steps
```bash
kubectl describe pod <pod-name> -n <namespace>   # check Events & Exit Code
kubectl logs <pod-name> --previous               # logs from the crashed container
kubectl get events --sort-by='.lastTimestamp' -n <namespace>
```

## Fix
- Exit code 1: fix application startup error (check logs with `--previous`).
- Exit code 137: OOMKilled — increase `resources.limits.memory`.
- Exit code 126/127: fix CMD/ENTRYPOINT path.
- Add `initialDelaySeconds` to livenessProbe if the app takes time to boot.
- Use `readinessProbe` to prevent traffic before app is ready.

## Reference
https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/
tags: kubernetes crashloop pod restart k8s exit-code container
