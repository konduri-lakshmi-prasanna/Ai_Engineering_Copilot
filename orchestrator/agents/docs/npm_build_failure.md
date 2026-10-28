# npm Build Failure (npm run build / CI scripts)

## Problem
`npm run build` exits with a non-zero code, causing CI/CD pipelines to fail. This prevents updated static assets from being produced or the application from being deployable.

## Common Causes and Fixes

### 1. Missing script in package.json
**Error**: `npm ERR! missing script: build`
**Fix**: Add the `build` script to `package.json`:
```json
"scripts": { "build": "react-scripts build" }
```

### 2. Environment variable not set
**Error**: `REACT_APP_API_URL is not defined`
**Fix**: Add the variable to `.env.production` or pass it via CI secrets:
```bash
REACT_APP_API_URL=https://api.example.com npm run build
```

### 3. TypeScript / ESLint compile errors treated as errors in CI
**Error**: `Failed to compile. TypeScript error in src/App.tsx`
**Fix**: Resolve the TypeScript error, or set `CI=false` only temporarily for diagnosis (do not ship with warnings suppressed permanently).

### 4. Node version mismatch
**Error**: `SyntaxError: Unexpected token '.'` or `engine "node" is incompatible`
**Fix**: Pin Node version with `.nvmrc` or `engines` in `package.json`. Use `nvm use` or Docker image with correct version.

### 5. Out-of-memory during webpack build
**Error**: `FATAL ERROR: Reached heap limit`
**Fix**: Increase Node heap: `NODE_OPTIONS=--max-old-space-size=4096 npm run build`

## Reference
https://docs.npmjs.com/cli/v9/commands/npm-run-script
https://create-react-app.dev/docs/deployment/
tags: npm build script react typescript ci webpack oom heap
