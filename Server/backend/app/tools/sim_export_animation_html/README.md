# sim.export_animation_html

Read-only artifact tool that exports the current project as the V21.4.4.3.3-compatible, single-file offline WebGL2 animation player.

V2.5.1.4 behavior:

- generates/replays the authoritative MuJoCo `trajectory.npz` used by native Viewer semantics instead of rebuilding qpos from commanded offsets;
- preserves dynamic gravity/contact/equality/passive motion and kinematic closure-solved qpos;
- reuses the native Viewer distance sampler/evaluator;
- never smooths physical distance values or nearest-point endpoints across frames.
