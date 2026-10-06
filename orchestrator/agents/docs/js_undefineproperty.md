---
title: TypeError - Cannot read properties of undefined / null
tags: TypeError, undefined, null, javascript, react, cannot read property
url: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Errors/Cannot_access_property
---
This error means code accessed a property (e.g. `data.user.name`) on a value
that turned out to be undefined or null at that point in execution — the
object itself was never assigned, an API call returned an unexpected shape,
or a React prop/state value hadn't loaded yet when the render happened. It
almost never means the property name is wrong; it means one of the objects
in the chain doesn't exist yet. Fix: trace back to where that value is
first set (API response, prop, state initializer) and either guard with
optional chaining (`data?.user?.name`) and a sensible default, or fix the
upstream logic so the value is guaranteed to exist before this line runs.