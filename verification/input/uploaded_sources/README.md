# DAO Governance Observatory (`dao_observatory`)

Reproducible behavioural telemetry pipeline and replication package (Appendix M) for the doctoral dissertation:
**"Integrating Gamification into DAO-Based Governance: A Framework for Enhancing Stakeholder Participation"** (Riga Technical University, 2026).

---

## 1. Overview & Architecture

The **DAO Governance Observatory** retrieves public off-chain governance records from the [Snapshot Hub GraphQL API](https://hub.snapshot.org/graphql) and indicative token-holder counts from Blockscout v2 APIs across **30 protocol DAOs** selected by a reproducible median-participation rule in the 12-month observation window **2025-10-01 to 2026-09-30 UTC** (with comparison window **2024-10-01 to 2025-09-30 UTC**).

### Indicators Computed (Table 2.1 / Table 3.13)
* **Breadth**: Proposals with votes, total votes cast, unique voting addresses, median voters per proposal (full window, H1, H2, prior year), active-electorate turnout, indicative token holders (`Token holders`), and `Holders minus voters`.
* **Concentration (P2 & Thesis 5)**: Per-proposal and window-level Gini coefficient on voting power (`VP > 0`), Nakamoto coefficient (50% threshold), Top-1 / Top-5 / Top-10 shares, and Herfindahl–Hirschman Index (HHI).
* **Continuity (Outcome 2, $\tau^*_2$, P3)**: Identified-core proxy (addresses voting on $\ge 50\%$ of proposals with votes in the window), core VP share (`Core VP share, %`), and year-on-year core retention (`--prior-votes`).
* **Deliberation (P1)**: Share of votes accompanied by a non-empty written rationale (`Reason share, %`).
* **Instrument Class ($\tau$, P7, Thesis 5)**: Automated coding of strategy definitions into `T` (token balance), `D` (delegated votes), `L` (locked/staked/vesting), `N` (NFT-based), `W` (whitelist/allocation), and `C` (contract-defined).

---

## 2. Quickstart: Local Execution (Mode B)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the 11 automated unit & end-to-end tests
python -m pytest -q tests

# 3. Set secret pseudonymisation salt (or let the tool generate data/raw/PRIVATE_pseudonym_salt.txt)
export DAOOBS_SALT="your-secret-random-salt-string"   # PowerShell: $env:DAOOBS_SALT="your-secret-random-salt-string"

# 4. Run Full Mode B (all 30 DAOs + token holders + prior-year core retention)
python -m dao_observatory run --config config/top30_2025-10_2026-09.json --holders --prior-votes
```

### Generated Outputs in `results/`
* `results/summary_by_dao.csv` — Complete 30-DAO table with all Mode B columns (`unique_voters`, `median_gini`, `median_nakamoto50`, `core_vp_share_pct`, `reason_share_pct`, `token_holders`, `holders_minus_voters`).
* `results/dissertation_table_3_13_full.md` — Ready-to-paste Markdown table for Dissertation **Table 3.13** (`§3.2.10`) plus empirical correlation summary for **P1** and **P2**.
* `results/appendix_M4_top10_all30.md` — Ready-to-paste Top-10 + remainder voter distribution tables for all 30 DAOs (**Appendix M.4**).
* `results/dao_observatory_results.xlsx` — Consolidated Excel workbook (`summary_by_dao`, `proposals_all`).
* `results/voters/voters_<space>.csv` — Pseudonymised voter-level tables for each of the 30 DAOs.
* `results/proposals/proposals_<space>.csv` — Proposal-level metrics for each of the 30 DAOs.
* `results/figures/lorenz_<space>.png` — High-resolution Lorenz curve and Top-10 voter bar charts for each DAO.

---

## 3. Running Directly on GitHub (GitHub Actions Cloud Execution)

You can also run Mode B directly on GitHub's cloud runners without keeping your local machine open:
1. Go to your GitHub repository **Settings → Secrets and variables → Actions** and add a New repository secret named `DAOOBS_SALT`.
2. Open the **Actions** tab → select **Run DAO Governance Observatory (Mode B)** → click **Run workflow** (`run_full_telemetry = true`).
3. When finished (~25–35 minutes), download the `dao-observatory-mode-b-results` ZIP artifact or pull the committed files from the `results/` folder.

---

## 4. Ethics, GDPR & Data Availability Statement

In accordance with Regulation (EU) 2016/679 (GDPR Art. 4(1) and Recital 26), voter addresses in public outputs are replaced with salted SHA-256 pseudonyms (`V<10 hex chars>`). Files matching `PRIVATE_*` (containing the pseudonymisation salt and raw address mappings) are automatically excluded from version control via `.gitignore` and must never be published.
