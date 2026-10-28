# Kubernetes OOMKilled (Out of Memory)

## Problem
A container is killed by the Linux kernel's OOM (Out Of Memory) killer when it tries to allocate more memory than its `resources.limits.memory` allows. The pod restarts with exit code `137`.

## Signs
- `kubectl describe pod` shows `OOMKilled` in the `Last State` section.
- Exit code 137 (128 + SIGKILL signal 9).
- `kubectl top pod` shows memory near or at the limit just before the kill.
- Node events: `Evicted` or `OutOfMemory`.

## Common Causes
1. **Memory limit set too low** for the actual workload.
2. **Memory leak** — heap grows unboundedly due to a bug (e.g., growing cache, unclosed connections).
3. **Sudden spike** — large batch job, query returning huge dataset, uncompressed file loaded into RAM.
4. **JVM not honouring container limits** — older JVMs ignore cgroup limits; use `-XX:+UseContainerSupport`.

## Diagnosis
```bash
kubectl describe pod <pod-name> -n <namespace>    # check OOMKilled in Last State
kubectl top pod <pod-name> --containers           # live memory usage
kubectl logs <pod-name> --previous                # last output before kill
```

## Fix
- **Short-term**: Increase `resources.limits.memory` and `resources.requests.memory`.
- **Long-term**: Profile memory usage (`heaptrack`, `memory_profiler`, `jmap`), fix the leak.
- For JVM: add `-XX:+UseContainerSupport -XX:MaxRAMPercentage=75`.
- Implement pagination or streaming for large dataset queries.

## Reference
https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/
tags: kubernetes oom oomkilled memory limit exit-code-137 resources
