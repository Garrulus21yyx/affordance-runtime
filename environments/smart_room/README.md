# Smart-room cross-surface fixture

Start the fixture from the repository root:

```bash
docker compose -f environments/smart_room/docker-compose.yml up --build
```

Host ports are configurable with `SMART_ROOM_WOT_PORT`,
`SMART_ROOM_CONTROL_PORT`, `SMART_ROOM_DIRECTORY_PORT`, and
`SMART_ROOM_DASHBOARD_PORT`, so parallel fixtures do not require deleting
existing containers. When the WoT host port changes, open the dashboard with
`?wot=http://localhost:<port>` so its browser-side polling uses the same port.

| Service | URL | Purpose |
|---|---|---|
| Dashboard | `http://localhost:3000` | DOM and screenshot surface |
| WoT servient | `http://localhost:8080/<thing>` | Live TD and device operations |
| Failure control | `http://localhost:8081` | Reset and deterministic WoT faults |
| Thing directory | `http://localhost:8082/things` | Runtime TD discovery |

DOM faults can be enabled with `?fault=selector_mutation,layout_shift` or the
page hook `window.__injectFault(name)`. WoT faults are set with:

```bash
curl -X POST http://localhost:8081/failure \
  -H 'content-type: application/json' \
  -d '{"thing":"thermostat","type":"timeout","delay_ms":1500}'
curl -X POST http://localhost:8081/reset
```

The copied `wot_td/` files are parser/security fixtures. Live execution should
prefer TDs discovered from the running servient.
