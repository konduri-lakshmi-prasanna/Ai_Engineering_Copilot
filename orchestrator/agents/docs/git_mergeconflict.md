---
title: Git merge / rebase conflict
tags: git, merge conflict, rebase, diverged, reset, cherry-pick
url: https://git-scm.com/book/en/v2/Git-Branching-Basic-Branching-and-Merging
---
A merge conflict means Git found overlapping changes to the same lines in
two branches and can't automatically decide which to keep. This is common
after history-rewriting operations like `git reset --soft`, force-pushes,
or when two collaborators edit the same file on diverged local histories.
Conflict markers (<<<<<<<, =======, >>>>>>>) appear directly in the file
and must be resolved by hand before committing. Fix: open each conflicted
file, decide which side (or a combination) is correct, remove the conflict
markers, then `git add` the resolved files and continue the merge/rebase.
To avoid repeat conflicts from diverged history, make sure all collaborators
pull/rebase from the same shared branch after any force-push or history
rewrite, rather than continuing to build on their old local commits.