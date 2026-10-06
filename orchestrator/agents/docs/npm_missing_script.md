---
title: npm error - missing script
tags: npm, node, script, package.json, start, build, react, deployment
url: https://docs.npmjs.com/cli/v10/using-npm/scripts
---
"npm ERR! missing script" means the script name you ran (e.g. `npm run start`,
`npm run build`) does not exist under the "scripts" key in package.json.
This is a ground-truth check, not a guess: open package.json and look at the
"scripts" object directly. Common causes: the script was renamed or removed
in a recent commit, the deploy platform's build command doesn't match what's
actually defined (e.g. platform runs `npm run build` but package.json only
has "build:prod"), or the wrong package.json is being picked up because the
frontend lives in a subdirectory and the deploy root is misconfigured.
Fix: either add the missing script to package.json, or change the deploy
platform's configured build/start command to match an existing script name.