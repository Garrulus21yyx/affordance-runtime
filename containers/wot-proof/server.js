/* Minimal reversible node-wot fixture for Coordinator conformance evidence. */
"use strict";

const http = require("http");
const { Servient } = require("@node-wot/core");
const { HttpServer } = require("@node-wot/binding-http");

const INITIAL = { enabled: false };
let state = structuredClone(INITIAL);
let history = [];

function setEnabled(enabled, source) {
  state.enabled = Boolean(enabled);
  history.push({ effect: "conformance.write", enabled: state.enabled, source });
}

function readBody(request) {
  return new Promise((resolve, reject) => {
    let body = "";
    request.on("data", (chunk) => (body += chunk));
    request.on("end", () => {
      try {
        resolve(JSON.parse(body || "{}"));
      } catch (error) {
        reject(error);
      }
    });
    request.on("error", reject);
  });
}

function sendJson(response, status, payload) {
  const body = JSON.stringify(payload);
  response.writeHead(status, {
    "Content-Type": "application/json",
    "Content-Length": Buffer.byteLength(body),
  });
  response.end(body);
}

function startControlPlane(port = 8081) {
  const server = http.createServer(async (request, response) => {
    try {
      if (request.method === "GET" && request.url === "/health") {
        return sendJson(response, 200, { ok: true, implementation: "node-wot-0.9.2" });
      }
      if (request.method === "GET" && request.url === "/state") {
        return sendJson(response, 200, { state, history });
      }
      if (request.method === "POST" && request.url === "/reset") {
        state = structuredClone(INITIAL);
        history = [];
        return sendJson(response, 200, { ok: true, state });
      }
      if (request.method === "POST" && request.url === "/set") {
        const payload = await readBody(request);
        setEnabled(payload.enabled, payload.source || "control");
        return sendJson(response, 200, { ok: true, state });
      }
      return sendJson(response, 404, { error: "not_found" });
    } catch (error) {
      return sendJson(response, 400, { error: `${error.name}: ${error.message}` });
    }
  });
  server.listen(port, "0.0.0.0", () => console.log(`conformance control plane ready on :${port}`));
}

async function main() {
  const servient = new Servient();
  servient.addServer(new HttpServer({ port: 8080 }));
  const wot = await servient.start();
  const thing = await wot.produce({
    "@context": "https://www.w3.org/2022/wot/td/v1.1",
    title: "affordance-runtime-conformance",
    id: "urn:affordance-runtime:conformance",
    securityDefinitions: { nosec_sc: { scheme: "nosec" } },
    security: "nosec_sc",
    properties: {
      enabled: { type: "boolean", readOnly: true },
    },
    actions: {
      setEnabled: { input: { type: "boolean" }, safe: false, idempotent: true },
    },
  });
  thing.setPropertyReadHandler("enabled", async () => state.enabled);
  thing.setActionHandler("setEnabled", async (input) => {
    const value = input ? await input.value() : true;
    setEnabled(value, "wot");
  });
  await thing.expose();
  startControlPlane();
  console.log("real node-wot conformance Thing ready on :8080");
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
