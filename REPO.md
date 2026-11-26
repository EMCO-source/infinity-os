# Sam-CloudeSpace — Android backend & iOS build

Private repo for the Sam-CloudeSpace project.

## Contents

- `gateway.py`, `slot.py`, `HOST.md`, `GATEWAY.md`, `README.md`, `tests/` — the AndroidServer kit
  (official Android Emulator slots behind an HTTPS gateway). See `README.md` (Arabic) for setup.

## GitHub Actions workflows

- **`android-emulator-test`** (`.github/workflows/android-emulator-test.yml`) — CI smoke test.
  On push to `main` or manual run: enables KVM on the Ubuntu runner, installs the host
  dependencies and the Android 35 Google Play system image, runs the unit tests, prepares
  slot 1, boots the emulator and waits for `sys.boot_completed`.
  Testing only: Actions jobs stop when they finish; it is not a hosted server.
- **`ios-ipa-build`** (`.github/workflows/ios-ipa-build.yml`) — manual workflow that builds an
  unsigned IPA for sideloading (AltStore) once the Xcode project source is added to this repo.
  Pass the scheme name when running it (default `SamCloudeSpace`).

## Free-plan compute (personal account)

- Actions: 2,000 minutes/month free on private repos (macOS minutes count 10x).
- Codespaces: 120 core-hours/month, but no usable KVM there — use the Actions workflow
  above for emulator testing.
