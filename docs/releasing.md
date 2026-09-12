# Releasing AIDSE Desktop

Updates reach installed copies through GitHub Releases. The app checks
`https://github.com/HamoudAl-Jowlahi/AIDSE-Desktop/releases/latest/download/latest.json`
once a day, compares the version there against its own, and offers to install
a newer one. Nothing is uploaded — the check is a single GET.

## The signing key

Every installer is signed with a minisign key. The matching **public** key is
compiled into `src-tauri/tauri.conf.json`, and the app refuses to install
anything that key does not verify. This is the only thing standing between a
user and an installer swapped out in transit, so it matters more than it looks.

Generate the keypair once:

```bash
npm run tauri signer generate -- -w "$HOME/.tauri/aidse.key"
```

It asks for a password and writes two files:

| File | What it is | Where it belongs |
| --- | --- | --- |
| `~/.tauri/aidse.key` | private key | your machine, and the `TAURI_SIGNING_PRIVATE_KEY` repository secret. **Never** in the repository. |
| `~/.tauri/aidse.key.pub` | public key | `plugins.updater.pubkey` in `src-tauri/tauri.conf.json`, committed |

Then add two repository secrets under **Settings → Secrets and variables →
Actions**:

- `TAURI_SIGNING_PRIVATE_KEY` — the full contents of `aidse.key`
- `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` — the password you chose

**If the private key is lost, no update can ever be pushed to an existing
install again.** Installed copies carry the old public key and will reject
anything signed with a new one; the only way back is asking every user to
download and run a fresh installer by hand. Back the key up somewhere you
would trust with a password manager's export.

## Cutting a release

`latest.json` takes its version from `src-tauri/tauri.conf.json`, not from the
tag, so the two have to agree. The workflow checks this and fails the build
rather than publishing an installer no running app believes is newer.

1. Bump the version in all three places:
   - `src-tauri/tauri.conf.json` → `version`
   - `src-tauri/Cargo.toml` → `package.version`
   - `package.json` → `version`
2. Commit the bump.
3. Tag and push:

   ```bash
   git tag v0.2.0 && git push origin master --tags
   ```

The `Release` workflow then builds the PyInstaller backend, builds the static
frontend, produces the signed NSIS installer, and opens a **draft** release
carrying the installer, its `.sig`, and `latest.json`.

4. Review the draft on GitHub and press **Publish release**.

Until you publish it, `releases/latest` still points at the previous release
and no user sees anything. That is deliberate: the draft is the last chance to
catch a bad build before it installs itself on other people's machines.

## What the user sees

A toast in the bottom-right corner, once a day at most, never a modal. It
names the version, offers **Install and restart** or **Later**, and dismissing
it silences that specific version permanently — a later one still surfaces.
There is also a **Check for updates** button under *Settings → Diagnostics &
About*, which reports the outcome either way instead of staying silent.

The install itself downloads the NSIS installer, verifies the signature,
runs it in passive mode (a progress bar, no prompts), and relaunches the app.

## Notes

- The build takes roughly 30–40 minutes cold, most of it PyInstaller walking
  the ML dependency tree. The Rust cache makes reruns much faster; the Python
  side is not cached.
- Only Windows is built. There is no macOS or Linux target configured, and the
  backend spec is Windows-specific.
- `infrastructure/github-actions/ci.yml` is left over from the multi-tenant
  server era and is not in `.github/workflows/`, so GitHub never runs it.
