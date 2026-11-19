# lmemory (JavaScript / TypeScript)

Ask your [Lmemory](https://github.com/TinkCarlos/Lmemory) memory from Node 18+: the page that answers, its
one-line answer, or "not in the vault". No dependencies; it speaks MCP to Lmemory's own server.

```js
import { Lmemory } from "lmemory";

const kr = Lmemory.local();                     // starts the local server over stdio (after the one-line install)
const a = await kr.ask("how do we ship a release?");
a.page;      // the page it came from
a.how;       // the one-line answer
a.refused;   // true when the memory does not know
await kr.close();

const team = Lmemory.remote("https://lmemory.example/mcp/team", { token: process.env.LMEMORY_TOKEN });
```

`Lmemory.local({ vault, python, server })` picks another vault, interpreter or server path. Tests:
`node --test test/lmemory.test.js` (runs the real server over stdio and HTTP). Not published to npm yet.
