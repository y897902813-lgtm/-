MuJoCo Studio V2.16.11.6 Integrated Full Source

Server / Studio / Lab 2.16.11.6; Client 0.3.9; VZ 0.3.2.1.
Based on complete V2.16.11.1 Unified Network Config source.

Service lifecycle (Server/):
- `python run.py` / `python run.py start` launches Hub + the integrated VZ.
- Ctrl+C stops Hub and its owned VZ child, releasing both listening ports.
- `python run.py stop` safely stops the managed Hub + VZ from a second SSH terminal.
- `python run.py status` reports the tracked PIDs without terminating anything.
- Only PID + process-birth + script-verified owned processes are terminated.
  Unknown holders of Hub/VZ ports are NOT reused, adopted or killed.
- Linux one-time legacy VZ recovery: `python run.py stop --legacy-vz`
  checks port socket ownership and the exact VZ script before terminating.
- The Client 0.3.9 local bridge (default 8766) is on the *user PC*;
  stopping the Server cannot stop a separate remote Client.
- Docker Compose services are managed by `python docker_ports.py down`.
- Same Server/ports.json config; Client destination server_ip defaults to 10.13.90.107.

Tests and hashes are packaged separately in the Development Evidence ZIP.
Real Linux loopback VZ process tests passed; Windows native MuJoCo and
production SSH/Docker stacks require deployment verification.

--- Original V2.16.11.1 unified-network release note ---

MuJoCo Studio V2.16.11.1 Integrated Full Source

Server / Studio / Lab 2.16.11.1; Client 0.3.9; VZ 0.3.2.1.

Network-port maintenance (same version, no business/protocol migration):
- Edit ONLY `Server/ports.json` for the Client target server IP (server_ip,
  default 10.13.90.107) and Hub / local Client bridge / integrated VZ ports.
- Start `python Server/run.py`; browser and integrated VZ read effective port config.
- For Docker, use `cd Server && python docker_ports.py up --build -d`.
- When Client runs on a separate PC, copy Server/ports.json to that PC's
  Client/ports.json and restart it. Keep Client bound to 127.0.0.1.
- Existing IP/port environment overrides take precedence. See Server/DEPLOYMENT.md.

Based on complete V2.16.11 source. No ProjectSpec/V21.5 protocol change.

Changes in V2.16.11.1:
- Hub baseline use presents an explicit asset choice, defaulting to reuse an
  existing category-scoped public mesh folder; copying frozen assets is opt-in.
- Strict server mesh filename validation prevents broken bindings; old fork
  clients that omit strategy retain V2.16.11's copy-frozen behavior.
- Animation background progress is portaled to document body above result axes.
- Hub Delivery Inspector has a background refresh for NX/Gantt/JSON/XML,
  leaving animation HTML, delivery tables and TSJSON unchanged.
- Tests and exact hashes: separate Development Evidence ZIP.

MuJoCo Studio V2.16.11 Integrated Full Source

Server / Studio / Lab 2.16.11; Client 0.3.9; VZ 0.3.2.1.
Based on the complete V2.16.10.2 package. No change to ProjectSpec, Viewer,
client data protocols or measurement accuracy.

Changes in V2.16.11:
- Using a baseline from Hub now acknowledges with HTTP 202/job_id and copies
  public meshes, model assets, tables and delivery in existing JobManager heavy lane.
- Repeat requests by the same owner/lease/source/copy name reuse the in-flight Job.
- Pending copies remain hidden until fully verified and published; cancellation,
  errors, and expired sessions roll back the working model and public mesh copy.
- Hub project scanning does not descend into each project's large mesh/results/
  delivery subtrees. Summary list no longer runs cold-cache expensive badges or
  VZ reconciliation in the first request; optional metadata is loaded separately.
- Hub paints actual project cards before awaiting model types/trash; transient
  errors show an explicit recovery notice with bounded automatic retries.
- Existing synchronous POST /api/projects/{id}/fork remains compatible;
  the Hub uses the optional ?background=true mode. Job polling/ACL unchanged.
- Actual network latency and Windows native MuJoCo/real large STL data are not
  validated in this environment. See the separate development evidence ZIP.

--- Prior release notes ---

MuJoCo Studio V2.16.10.2 Integrated Full Source

Server / Studio / Lab 2.16.10.2; Client 0.3.9; VZ 0.3.2.1.
Builds on V2.16.10.1 without modifying the ProjectSpec/Viewer/API or data protocol.

Changes in V2.16.10.2:
- Result charts: clearer softly tinted command bar with stronger module distinction from axis cards.
- Drive setup: drag the vertical divider in two-column view to resize left/right drive panes.
- ArrowLeft/ArrowRight and Home/End work on the separator; double-click resets to 50/50.
- Narrow editor windows / Quick Optimization automatically use one column, restoring the split when space returns.
- The split is transient UI session state; drive ordering, physics and saved models remain unchanged.
- See the separate V2.16.10.2 Development Evidence ZIP for test cases, diffs and hashes.

--- Prior release notes ---

MuJoCo Studio V2.16.10.1 Integrated Full Source

Server / Studio / Lab 2.16.10.1; Client 0.3.9; VZ 0.3.2.1.
Upgrades V2.16.10 in place; preserves ProjectSpec, assets/tables, distance computations, Viewer and Lab protocol compatibility.

Changes in V2.16.10.1:
- Gantt segment editor dropdown labels are now "行程 / 结束位置" and "速度 / 时长" (no "表达式" suffix).
- Press Enter in the Gantt editor's text inputs to invoke the same Save handler as the Save button.
- Cancel, top-right close and Escape never save; Enter inside the editor never launches a whole simulation.
- No new API, business tools, persistent model fields, dependencies or data migrations.

Highlights in V2.16.10:
- Hub model properties include "Table Assets" under model-private assets/tables.
- Mapping and external-motion CSV imports first atomically back up the original table, then embed points into the model.
- Mapping and external-motion CSV exports first update the same stable table asset, then download exact embedded values.
- One file per model + table type + drive/segment ID; repeated operations overwrite rather than duplicate.
- Result axis CSV / merged CSV / Excel-readable TSV exports also upsert stable table assets before delivery/download.
- Existing V2.16.9.1 axis UI and default distance-pair layout remain unchanged.

Unchanged V2.16.9 functionality:
- Only compute selected exact pair:<id> sources, including custom result layouts.
- Batch GET pair_id=A&pair_id=B and POST {"pair_ids":["A","B"]};
  legacy no-selection and /{pair_id} endpoints remain compatible.
- Reuse one heavy-lane Job per frozen snapshot/owner/lease, append pending pairs;
  share mesh points, immutable KD trees, model and trajectory between waves.
- Safe Enter trajectory reuse requires server-verified solver-input identity
  and asset digest; physical changes always require simulation.
- No changes to Client 0.3.9, VZ 0.3.2.1, persistent model JSON or tool pool.

Native Windows MuJoCo + actual meshes, browser WebGL2 and p50/p95 latency gate
are NOT validated in this environment. See independent V2.16.10.1 development archive for this patch and V2.16.10 for the earlier features.

Stop the previous Server before replacing. Back up Server data, project baselines
and formal archives. Never run two versions against one mutable data directory.
