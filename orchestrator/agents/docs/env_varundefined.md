---
title: Undefined / missing environment variable at runtime
tags: env, environment variable, KeyError, undefined, dotenv, config, secrets, .env
url: https://12factor.net/config
---
Errors like Python's KeyError on os.environ[...], os.getenv(...) returning
None where a value was assumed, or Node's process.env.X being undefined,
almost always mean the environment variable was never set in the environment
the app is actually running in. This is especially common right after a
deploy, because a local ".env" file works during development but is
gitignored and never uploaded to the hosting platform. Fix: set the
required variable directly in the hosting platform's environment/config
panel (not just the local .env file), and add a startup check that fails
fast with a clear message if a required variable is missing, rather than
letting the app crash deep inside unrelated code.