# Publishing guide (no Windows PC needed)

This repository contains the finished report in two forms:

- **Power BI Project (PBIP)** in `powerbi/project/`: `StJohnsEconomy.pbip`, the
  semantic model in TMDL (`StJohnsEconomy.SemanticModel/`) and the report in PBIR
  (`StJohnsEconomy.Report/`). Opening the `.pbip` in Power BI Desktop shows the
  finished four-page report; the data loads from this repository's CSV files on
  GitHub.
- **Web version** in `docs/` (`docs/index.html`), a static site with the same
  pages, data and KPIs.

Power BI Desktop runs only on Windows, so the routes below are ordered from "works
today on a Mac with no Microsoft licence" to "needs a Windows machine". Licensing
and product facts were checked on 2026-10-17 against the Microsoft pages listed
under [Sources](#sources) (each with its "last updated" date). Where Microsoft's
pages disagree or are silent, this guide says so.

## Route 1: GitHub Pages (free, public, works from a Mac)

Publishes the web version, not the Power BI file.

1. Push the repository to GitHub as `mrw-soumik/stjohns-economy-powerbi`.
2. On GitHub: Settings > Pages > Build and deployment > Source: "Deploy from a
   branch"; Branch: `main`, folder `/docs`; Save.
3. After a minute the site is at
   `https://mrw-soumik.github.io/stjohns-economy-powerbi/`. Add that link to the
   README ("View the live report" or a separate "Web version" link).

`docs/.nojekyll` makes GitHub Pages serve the files as they are. The site has no
third-party requests (D3 is vendored), no cookies and no tracking.

## Route 2: Microsoft Fabric Git integration (browser only, works from a Mac)

The Power BI service in the browser connects a workspace to this GitHub repository
and imports the PBIP items, so no one needs to open Power BI Desktop.

**Requirements**

- A **work or school account** (Microsoft Entra ID). Consumer addresses such as
  Gmail, Outlook.com or Hotmail cannot sign up [S18]. Without an employer
  tenant, a Microsoft 365 business trial creates an `onmicrosoft.com` tenant but
  needs a credit card and must be cancelled within 30 days to avoid charges
  [S18]. The Microsoft 365 Developer Program sandbox, which includes Power BI
  Pro, is now limited to Visual Studio Professional or Enterprise subscribers,
  Microsoft partners and Premier or Unified Support customers [S20].
- A workspace on **Fabric capacity or Power BI Premium capacity**. A Fabric trial
  capacity counts: "You can only connect to Git repos if you have a valid Premium
  license ... This applies to trial licenses as well" [S2][S1]. Pro workspaces
  and My workspace cannot connect [S3]. Premium Per User is described as
  supported on one planning page [S32] but not on the Git integration pages
  [S1][S2]; treat it as unsupported unless your tenant offers it.
- The **Fabric trial** lasts 60 days and provides an F4 or F64 trial capacity,
  plus a Power BI trial with Premium Per User features; eligibility is not
  guaranteed [S17]. (The licences page describes the trial as 64 capacity units
  [S34]; the trial page says F4 or F64.)
- Two **tenant settings** in the Fabric admin portal: "Users can synchronize
  workspace items with their Git repositories" (on by default) and "Users can
  sync workspace items with GitHub repositories" (off by default) [S5]. If you
  are not the tenant administrator, ask them to turn the second one on.
- **GitHub on github.com** (cloud only) and a personal access token: either
  fine-grained with "Contents" read and write on this repository, or classic with
  the `repo` scope [S1][S4]. Microsoft still lists Git integration for Power BI
  items as a preview feature [S4].

**Steps**

1. Sign in at `https://app.powerbi.com` (Safari on a Mac is supported [S29]).
2. Create a workspace and assign the trial or Fabric capacity to it
   (Workspace settings > License info).
3. Workspace settings > Git integration > GitHub > Add account (paste the
   token). Choose the repository, branch `main` and folder `powerbi/project`,
   then select Connect and sync [S1]. Fabric recognises item folders named
   `{display name}.{item type}` that contain a `.platform` file [S6]; this
   project has `StJohnsEconomy.SemanticModel` and `StJohnsEconomy.Report`, and
   the report's `byPath` link to its semantic model works with Git
   integration [S7]. On the first sync the empty side receives the other side's
   content [S3].
4. Only metadata arrives, not data [S8]. Open the semantic model's Settings >
   Data source credentials > Edit credentials for `https://raw.githubusercontent.com`:
   authentication **Anonymous**, privacy level **Public**, and clear "Skip test
   connection" [S9]. Privacy levels are not published from Desktop, so they
   always need setting in the service [S10].
5. Select Refresh now. The queries use `Web.Contents` with a fixed root URL and a
   `RelativePath`, which the service can refresh [S10].
6. Optional: Scheduled refresh (up to 8 a day on shared capacity, 48 on
   Premium, Premium Per User or Fabric [S10]). A schedule turns off after four
   consecutive failures and pauses after two months without report views [S11].
   Statistics Canada updates these tables monthly, so weekly is plenty.

## Route 3: Deploy from the Mac with Python (fabric-cicd)

`fabric-cicd` is Microsoft's Python library for deploying Fabric and Power BI
items from a repository; it runs on macOS and supports interactive browser
sign-in [S15][S16].

```bash
python3 -m venv .venv-deploy && source .venv-deploy/bin/activate
pip install fabric-cicd azure-identity
python - <<'PY'
from azure.identity import InteractiveBrowserCredential
from fabric_cicd import FabricWorkspace, publish_all_items

workspace = FabricWorkspace(
    workspace_name="St. John's Economy",            # an existing workspace you can edit
    repository_directory="powerbi/project",
    item_type_in_scope=["SemanticModel", "Report"],
    token_credential=InteractiveBrowserCredential(),
)
publish_all_items(workspace)
PY
```

- The library needs the `.platform` files (present) and converts the report's
  `byPath` dataset reference to `byConnection` automatically [S16]; the Fabric
  REST API itself only accepts `byConnection` for reports [S7][S12].
- After the first deployment, set the data source credentials and refresh as in
  Route 2, steps 4 to 6 [S15].
- **Workspace licence: unconfirmed.** The REST API says creating a Power BI item
  needs "the appropriate license" [S12] and the library skips its capacity check
  for reports and semantic models [S16], which suggests a Pro workspace may
  work, but an older guidance page says "Fabric REST APIs only work with
  Fabric" [S33]. Expect to need a Fabric or trial capacity.
- This script has not been run against a tenant from this repository.

The Fabric CLI (`pip install ms-fabric-cli`, `fab auth login`, `fab import`) also
runs on macOS [S13], but its import rejects reports that use `byPath` [S14], so
fabric-cicd is the simpler choice here.

## Route 4: Any Windows computer (Power BI Desktop)

**Requirements:** Windows 10 or Windows Server 2016 or later. Power BI Desktop
runs natively on Windows on ARM since October 2025, with the 2025-09 cumulative
update installed [S25][S26]. For virtual machines Microsoft lists only Azure
Virtual Desktop and Windows 365 as supported [S25]. On a Mac with an M1, M2 or
M3 chip, Microsoft authorizes Parallels Desktop (versions 18 to 20) to run
Windows 11 on Arm [S27]; later chips are not covered by that article.

**Steps**

1. Download or clone the repository.
2. Open `powerbi/project/StJohnsEconomy.pbip` in Power BI Desktop. PBIP and the
   PBIR report format are generally available and PBIR is the default; Desktop
   opens a PBIR report directly [S7][S28]. If prompted, allow the anonymous web
   connection to `https://raw.githubusercontent.com` and select Refresh.
3. Check the numbers: run the query at the end of `powerbi/measures.dax` in DAX
   query view and compare with `powerbi/check-query-expected.csv`.
4. Home > Publish to a workspace (sign in with a work or school account), or
   File > Save as `.pbix` and upload it later from the Mac at app.powerbi.com,
   which accepts `.pbix` files (not PBIP folders) [S31].

## Route 5: "Publish to web" (public link to the Power BI report)

Use this after the report is in the service (Route 2, 3 or 4) to get a public
link for the README.

- **What it does:** "anyone on the Internet can view your published report ...
  Viewing requires no authentication" [S21]. The data here is public Statistics
  Canada data, but check your organization's policy before publishing.
- **Licence:** "a Microsoft Power BI license to publish to web from My
  Workspace"; "a Pro or Premium Per User license to publish to web from
  workspaces" [S21]. Content in a Premium Per User workspace "isn't accessible
  to unlicensed users" [S22], so publish from My workspace or a Pro or capacity
  workspace.
- **Tenant setting:** "Publish to web" in the admin portal; only admins can allow
  the creation of new embed codes [S23]. The default for new tenants is not
  stated on the pages checked.
- **Behaviour:** data is cached for one hour, and a data refresh clears the
  cache [S21]. The person who created the embed code must stay licensed [S21].
- **Not supported:** row-level security, DirectQuery or live connections, shared
  semantic models, R and Python visuals, and Q&A [S21]. This report uses none of
  them (import mode, standard visuals only).
- **Steps:** open the report > File > Embed report > Publish to web (public) >
  Create embed code > copy the link. Paste it into the README under "View the
  live report".

"Embed report > Website or portal" (secure embed) is different: viewers must
sign in and need Pro or Premium Per User unless the content is on Premium or
Fabric F64 or larger capacity [S24].

## Which route to use

| Goal | Route | Microsoft licence needed |
|---|---|---|
| A public dashboard link today | 1 (GitHub Pages) | None |
| The real Power BI report online, from a Mac | 2 (Git integration) or 3 (fabric-cicd), then 5 | Work or school account; Fabric or trial capacity |
| Open and edit the report in Power BI Desktop | 4 (Windows) | None to open; an account to publish |

## Uncertain or unconfirmed (as of 2026-10-17)

- Whether Git integration works in Premium Per User workspaces (sources disagree).
- Whether fabric-cicd or the Fabric REST API can deploy Power BI items to a Pro
  workspace without capacity.
- The exact Fabric trial capacity size (F4 or F64) in a given tenant.
- The default state of the "Publish to web" tenant setting for new tenants, and
  whether embed codes keep working after a trial licence ends.
- Microsoft 365 Business trial details for creating a personal tenant.

## Sources

| ID | Page | Last updated |
|---|---|---|
| S1 | [Get started with Git integration](https://learn.microsoft.com/en-us/fabric/cicd/git-integration/git-get-started) | 2026-09-01 |
| S2 | [Troubleshoot CI/CD](https://learn.microsoft.com/en-us/fabric/cicd/troubleshoot-cicd) | 2026-09-23 |
| S3 | [Git integration process](https://learn.microsoft.com/en-us/fabric/cicd/git-integration/git-integration-process) | 2026-06-15 |
| S4 | [What is Git integration?](https://learn.microsoft.com/en-us/fabric/cicd/git-integration/intro-to-git-integration) | 2026-09-01 |
| S5 | [Git integration tenant settings](https://learn.microsoft.com/en-us/fabric/admin/git-integration-admin-settings) | 2026-10-07 |
| S6 | [Git integration source code format](https://learn.microsoft.com/en-us/fabric/cicd/git-integration/source-code-format) | 2025-12-15 |
| S7 | [Power BI Desktop project report folder](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-report) | 2026-09-23 |
| S8 | [Power BI Desktop projects (PBIP)](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-overview) | 2026-09-23 |
| S9 | [CI/CD tutorial](https://learn.microsoft.com/en-us/fabric/cicd/cicd-tutorial) | 2026-07-24 |
| S10 | [Data refresh in Power BI](https://learn.microsoft.com/en-us/power-bi/connect-data/refresh-data) | 2026-09-18 |
| S11 | [Configure scheduled refresh](https://learn.microsoft.com/en-us/power-bi/connect-data/refresh-scheduled-refresh) | 2026-02-13 |
| S12 | [Fabric REST API: Create Item](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/create-item) | 2026-10-05 |
| S13 | [Fabric CLI documentation](https://microsoft.github.io/fabric-cli/) | PyPI 1.7.0, 2026-08-19 |
| S14 | [Fabric CLI import source code](https://github.com/microsoft/fabric-cli/blob/main/src/fabric_cli/utils/fab_cmd_import_utils.py) | checked 2026-10-17 |
| S15 | [Deploy PBIP with fabric-cicd](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-deploy-fabric-cicd) | 2026-09-18 |
| S16 | [fabric-cicd constants (v1.4.0)](https://github.com/microsoft/fabric-cicd/blob/main/src/fabric_cicd/constants.py) | 2026-10-07 |
| S17 | [Fabric trial capacity](https://learn.microsoft.com/en-us/fabric/fundamentals/fabric-trial) | 2026-08-12 |
| S18 | [Sign up for Power BI as an individual](https://learn.microsoft.com/en-us/power-bi/fundamentals/service-self-service-signup-purchase-for-power-bi) | 2026-03-23 |
| S20 | [Microsoft 365 Developer Program FAQ](https://learn.microsoft.com/en-us/office/developer-program/microsoft-365-developer-program-faq) | 2026-09-04 |
| S21 | [Publish to web](https://learn.microsoft.com/en-us/power-bi/collaborate-share/service-publish-to-web) | 2025-11-01 |
| S22 | [Premium Per User FAQ](https://learn.microsoft.com/en-us/fabric/enterprise/powerbi/service-premium-per-user-faq) | 2025-05-27 |
| S23 | [Export and sharing tenant settings](https://learn.microsoft.com/en-us/fabric/admin/service-admin-portal-export-sharing) | 2026-04-08 |
| S24 | [Secure embed](https://learn.microsoft.com/en-us/power-bi/collaborate-share/service-embed-secure) | 2025-11-01 |
| S25 | [Get Power BI Desktop](https://learn.microsoft.com/en-us/power-bi/fundamentals/desktop-get-the-desktop) | 2026-10-09 |
| S26 | [Power BI Desktop update archive](https://learn.microsoft.com/en-us/power-bi/fundamentals/desktop-latest-update-archive) | 2026-08-18 |
| S27 | [Windows 11 on Mac computers with M1, M2 and M3 chips](https://support.microsoft.com/en-us/windows/options-for-using-windows-11-with-mac-computers-with-apple-m1-m2-and-m3-chips-cd15fd62-9b34-4b78-b0bc-121baa3c568c) | checked 2026-10-17 |
| S28 | [Edit PBIP files outside Desktop](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-external-editing) | 2026-09-23 |
| S29 | [Supported browsers for Power BI](https://learn.microsoft.com/en-us/power-bi/fundamentals/power-bi-browsers) | 2025-10-01 |
| S31 | [Get data from files](https://learn.microsoft.com/en-us/power-bi/connect-data/service-get-data-from-files) | 2025-02-28 |
| S32 | [Planning: integration with other services](https://learn.microsoft.com/en-us/power-bi/guidance/powerbi-implementation-planning-integration-with-other-services) | 2026-05-20 |
| S33 | [Planning: deploy content](https://learn.microsoft.com/en-us/power-bi/guidance/powerbi-implementation-planning-content-lifecycle-management-deploy) | 2024-12-30 |
| S34 | [Microsoft Fabric licences](https://learn.microsoft.com/en-us/fabric/enterprise/licenses) | 2026-06-15 |
