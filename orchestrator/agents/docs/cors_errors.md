---
title: CORS - blocked by browser cross-origin policy
tags: CORS, cross-origin, fetch, browser, access-control-allow-origin, frontend, api
url: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS
---
A CORS error happens in the browser, not the server: the frontend's origin
(e.g. https://app.vercel.app) made a request to a backend on a different
origin (e.g. https://api.onrender.com), and the backend's response didn't
include an Access-Control-Allow-Origin header that permits that frontend
origin. The request often still reaches the backend and even succeeds
server-side — the browser just refuses to hand the response back to the
page's JavaScript. Fix: configure CORS middleware on the backend
(e.g. FastAPI's CORSMiddleware) to explicitly allow the deployed frontend's
origin, and avoid leaving it as a wildcard "*" once credentials/cookies are
involved, since browsers reject wildcard origins combined with credentials.