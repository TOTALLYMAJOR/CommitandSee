# Set up the CommitandSee GitHub App

Portable builds starting with **v0.3.0-rc.1** and current source include CommitandSee's public
GitHub App registration.
Ordinary users can go directly to [installation and sign-in](#install-authorize-then-select-repositories);
they do not enter app IDs or register their own app. The publisher instructions
below are for maintaining that registration or configuring a fork.

The implementation uses device authorization and read-only repository
permissions. The published **v0.2.0-rc.1 Windows ZIP does not include GitHub
sign-in**; adding settings to that older build will not enable it.

For chart-to-PR lookup on private repositories (source and portable builds
starting with v0.4.0-rc.1), the publisher
can also enable **Pull requests: read-only**, and the installation owner must
accept the new permission. Existing installations can keep using history and
the browser-based PR search with their current permissions.

## Bundled public registration

| Field | Value |
| --- | --- |
| App | [CommitandSee](https://github.com/apps/commitandsee), owned by `TOTALLYMAJOR` |
| Client ID | `Iv23liOTvNR8YGvV0jow` |
| App slug | `commitandsee` |
| Numeric App ID | `5638377` — identification only, not the OAuth Client ID |

These identifiers are public, not credentials. A public GitHub API check matched
the registration and reported only Contents read and Metadata read permissions,
with no subscribed events. That check does not prove device authorization,
organization approval, or a private repository download. The separate live
source-preview check is recorded below.

## Register an app for a fork

Open your GitHub account or organization settings, then **Developer settings →
GitHub Apps → New GitHub App**. Use these settings:

| Setting | Value for CommitandSee |
| --- | --- |
| Name | An available publisher-owned name; `CommitandSee` is the existing official registration |
| Homepage | `https://github.com/TOTALLYMAJOR/CommitandSee` |
| Description | Read-only Git history visibility for repositories the user selects |
| Callback URL | Leave empty; device authorization does not use a callback server |
| Expire user authorization tokens | Enabled |
| Request user authorization (OAuth) during installation | Disabled; sign-in starts from the dashboard |
| Enable Device Flow | Enabled |
| Setup URL / Redirect on update | Leave unset |
| Webhooks → Active | Disabled; no webhook URL or secret |
| Repository permissions | **Contents: Read-only** and **Metadata: Read-only** |
| Pull requests | Optional **Read-only** for private chart-to-PR lookup |
| Other repository, organization, account, and enterprise permissions | No access |
| Where can this GitHub App be installed? | **Any account** |

Create the app. The name must be available globally; use the actual resulting
slug, not an assumed spelling. GitHub documents these settings in its
[registration guide](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/registering-a-github-app).
Contents permission is needed for Git history access; no write permission or
broad OAuth `repo` scope is required for this design. See
[GitHub App permissions](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app#choosing-permissions-for-git-access).

## Override the registration

Only do this when using a different publisher registration. From that app's
settings, copy its **Client ID**. This is different from its numeric
App ID. Copy the **app slug** from its public address:
`https://github.com/apps/<app-slug>`.

These two values are public configuration. **Do not supply a client secret,
private key, personal access token, or user access token.** CommitandSee's device
flow needs no embedded app secret. Do not generate or download a private key for
this client. GitHub describes the client-ID-based exchange in its
[device authorization documentation](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-user-access-token-for-a-github-app#using-the-device-flow-to-generate-a-user-access-token).

To override the bundled registration, add the public values to the existing
dashboard configuration, preserving its other fields:

```json
"github_app": {
  "client_id": "YOUR_PUBLIC_CLIENT_ID",
  "app_slug": "your-app-slug"
}
```

For normal use, omit this override and use `github_app_defaults.json` bundled
beside the application module. An explicit empty `github_app` object or blank
fields disables that default; environment variables can override either choice.
Restart after editing configuration. For the portable launcher, the default configuration is
`%LOCALAPPDATA%\CommitandSee\config.json`; for the source server, use the file
passed with `--config`.

Environment variables override those fields. They also work for portable builds
starting with v0.3.0-rc.1, without modifying the executable. For example, from
PowerShell in the extracted folder:

```powershell
$env:COMMITANDSEE_GITHUB_CLIENT_ID = "YOUR_PUBLIC_CLIENT_ID"
$env:COMMITANDSEE_GITHUB_APP_SLUG = "your-app-slug"
.\CommitandSee.exe
```

Or, for the current source implementation:

```bash
COMMITANDSEE_GITHUB_CLIENT_ID=YOUR_PUBLIC_CLIENT_ID \
COMMITANDSEE_GITHUB_APP_SLUG=your-app-slug \
python3 git_dashboard.py serve --config /absolute/path/to/config.json
```

These examples configure public identifiers; they do not sign in a user or grant
repository access.

## Install, authorize, then select repositories

1. Open [the CommitandSee installation page](https://github.com/apps/commitandsee/installations/new)
   (or your fork's `https://github.com/apps/<app-slug>/installations/new`). Select
   the personal account or organization that owns the repositories. Prefer **Only select
   repositories** and grant the repositories you want available to CommitandSee.
2. In the running dashboard, choose **Connect GitHub → Sign in with GitHub**.
   Open GitHub using the displayed link and enter the displayed device code there.
   Complete GitHub's authorization, then return to the dashboard.
3. Search the accessible repository list, check the repositories to monitor, and
   choose **Add selected**. Signing in alone does not add or download every
   repository. The picker selection determines what the dashboard saves.

Use **Cancel sign-in** to end a pending authorization attempt. **Close** closes
the picker; it does not disconnect an authorized session.

Installation and user authorization are separate: the user must have access and
the app installation must cover the repository. An organization may require
owner approval; **Request** is not an approved installation. After approval or
changing selected repositories on GitHub, return and use **Refresh list**. See
[GitHub installation and approval requirements](https://docs.github.com/en/apps/using-github-apps/installing-a-github-app-from-a-third-party).

The app reads the selected repositories' published default-branch history into
its own bare cache. This does not reveal local working files, stashes, unpublished
commits, PR status, or CI results. Add a **Local checkout** separately for local
work visibility. Repository lists, saved metadata, and snapshots can contain
private names and paths; treat exports as private until reviewed.

## Session credentials and saved data

Access and refresh tokens stay in the running app's memory. **Disconnect GitHub**
forgets them, and exiting the app requires a new sign-in next time. Closing only
the browser tab does not exit the app. Saved repository selections remain in the
companion registry. Disconnected authenticated sources show **Sign in required**
instead of their collected history; public and local sources continue normally.

Token expiration remains enabled. Device-authorized tokens can be refreshed
without a client secret while the app session is running; see
[GitHub's refresh contract](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/refreshing-user-access-tokens).
Local disconnect does not uninstall the app or revoke its GitHub authorization.
To withdraw the grant, manage the app in GitHub account or organization settings.

**Disconnect and Remove do not erase downloaded private Git objects from disk.**
Authenticated history remains in `github-repositories` beside observation state;
anonymous public sources use the separate `public-repositories` directory. Stop the
app before explicitly deleting its downloaded cache if you want that local copy
gone; future collection will need to download it again. Do not confuse deleting
an app cache with deleting an original checkout. Backups can also contain these
private objects.

## Setup and access problems

| Message or state | Check |
| --- | --- |
| GitHub sign-in is not configured | Use a complete build containing this feature and its bundled registration; maintainers using a fork should check both override values |
| Device flow is disabled | Enable Device Flow on the registered GitHub App |
| Invalid client credentials | Use the app's Client ID, not its numeric App ID, slug, or secret |
| Code expired or authorization declined | Start a fresh sign-in from the dashboard |
| Signed in, but no accessible repositories | Configure the app installation's repository selection; obtain organization approval where required |
| A repository is missing | Verify the selected account, your own access, the app installation, and any pending organization approval; refresh the list |
| Access was revoked or the session ended | Sign in again and verify the installation still grants the repository |
| GitHub is unavailable or rate-limited | Read the displayed error and retry when the service permits; an unavailable list is not proof that the account has no repositories |

## Validation boundary

The owner completed a real GitHub device sign-in in an isolated local source
preview and selected one private repository through the picker. The local HTTP
snapshot reported a connected session, one authenticated repository, one private
repository, available history for that repository, and zero collection errors.
This confirms that specific authorization and collection path; no account name,
repository identifier, device code, or token is retained in this record.

The source Python suite ran 145 tests: 141 passed and four platform-specific
checks were skipped. Browser validation passed 78 checks across Chromium,
Firefox, and WebKit, including 27 scoped axe accessibility checks. Offline
fixtures remain separate from the real-provider check above.

A native Windows candidate built from this implementation passed extracted-ZIP
local add/remove and restart checks, GitHub device-code issuance and cancellation,
clean restart with no retained session, and shutdown checks for pending sign-in
and active Git descendants. These native checks did not complete user login or
collect private history; the live source-preview check above is the evidence for
that path. These results do not establish general organization-policy, clean-machine,
release, or owner acceptance. The historical v0.2.0-rc.1 ZIP does not include GitHub
sign-in.

Never include live device codes or tokens in screenshots, support reports, or
committed fixtures.
