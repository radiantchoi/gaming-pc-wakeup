# T5-termux — Host gate on the Galaxy Note 8 (ABANDONED)

- Attempted by: the user, on the phone, 2026-09-19
- Outcome: `deploy/termux/install.sh` ran for a long time (pydantic-core
  source build under Rust, plus uv's "failed to hardlink, falling back to
  full copy" warning) and then failed. The error output was not captured.
  The user decided not to pursue the phone as a host and uninstalled Termux,
  Termux:Boot, and Tailscale from it.
- Consequence: the Raspberry Pi 1 Model B is the only host. `deploy/termux/`
  and the README's Host B section stay in the repository as untested
  reference material, marked "not pursued".
- No change to application code.
