# Changelog

All notable changes to ExpenseIQ are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

---

## [1.2.0] – 2026-05-28

### Added
- **Dark mode** in the browser emulator — switches automatically via `prefers-color-scheme: dark`. Remapped all colour tokens (blues, reds, surfaces, borders) for dark backgrounds.
- **Account deletion** from the Accounts screen — tap the ⋮ button on any account row to reveal Edit and Delete actions inline beneath the row.
- **Group deletion** from both the Accounts screen (trash icon in each group header) and the Group Manager. Deleting a group also removes all its accounts and their transactions, with a warning in the confirm dialog.
- **README.md** and **CHANGELOG.md** added to the project root.

### Changed
- **Account group types simplified** to four options: Others, Liquid Savings, Investments, Loan. Legacy types (Wallet, Spending Account, Credit Card) are automatically normalised to Others on load.
- **Investments** added as a new restricted group type, following the same balance rules as Liquid Savings and Loan.
- **Credit Card special-case columns** removed from the Accounts screen — credit cards are now treated as Others accounts with no separate "Balance Payable / Outstanding" columns.
- **Bottom navigation icons** replaced with outline SVG icons (document, bar chart, credit card, vertical dots). Active state uses a blue pill background instead of colour alone.
- **More tab** icons updated to match the same stroke-based SVG style as the bottom nav.
- **Theme overhaul**: deeper indigo wallpaper gradient, Dynamic Island–style notch, rounded-square transaction icons, `font-weight: 800` for key figures, subtler borders, backdrop-blur on modals and toasts.
- **Search icon** in the Transactions header replaced with a consistent outline SVG magnifying glass.
- **Add Group icon** in the Accounts header replaced with an outline folder-with-plus SVG.

### Fixed
- Dark mode: month-year text, day numbers, app bar titles, modal headings, settings labels, and status bar icons were rendering black. Fixed by adding `color: var(--text)` to `body` and explicit overrides on affected elements.

---

## [1.1.0] – 2026-05-28

### Fixed
- **Transfer balance bug**: transfers between a Liquid Savings/Loan account and an Others account were not appearing in the monthly income/expense totals, even when `affectsMainBalance` was correctly set to `true`.
  - Root cause 1 — `computeAffectsBalance` (browser) / `enrichAffectsMainBalance` (Android): non-restricted FROM accounts returned `true` immediately without checking whether the TO account was restricted, causing Wallet→Wallet and similar transfers to be incorrectly flagged.
  - Root cause 2 — `getMonthTotals` (browser) / `buildUiState` + `buildStats` (Android): the income/expense aggregation only filtered on `type === 'INCOME'` and `type === 'EXPENSE'`, silently dropping all `TRANSFER` rows regardless of `affectsMainBalance`.
  - Fix: qualifying transfers (Restricted ↔ Others) are now counted as income (Restricted→Others) or expense (Others→Restricted) in both the Transactions summary bar and the Stats totals.
- **Stats pie chart** now includes qualifying transfers as a "Transfer" slice when the direction matches the current Income/Expense view.
- `StatsViewModel` updated to receive accounts and groups so it can determine transfer direction without a database round-trip.

---

## [1.0.0] – 2026-05-28

### Added

#### Android app
- **Transactions screen** — daily-grouped list with month navigation, Income/Expense/Total summary bar, and FAB to add transactions.
- **Add/Edit Transaction screen** — type selector (Income / Expense / Transfer), amount field, date picker, account pill selector, category grid, note field.
- **Stats screen** — monthly pie chart (Canvas-drawn) and category breakdown list with percentages. Toggle between Expense and Income views.
- **Accounts screen** — net-worth summary (Assets / Liabilities / Total), accounts grouped by account group, tap to open account detail.
- **Account Detail screen** — per-account transaction history with its own month navigation and summary bar.
- **Account management** — add accounts with name, group, and opening balance. Opening balance does not count toward monthly income/expense totals.
- **Group management** — add custom account groups with a type selector (Others / Liquid Savings / Investments / Loan).
- **Category management** — add, edit, and delete income and expense categories with emoji icon and colour.
- **Room database** with five entities: AccountGroup, Account, Category, Transaction. Pre-seeded with default groups and 17 categories on first install.
- **Hilt DI** wired through Application, DAOs, Repository, and all ViewModels.
- **MVVM architecture** with reactive `StateFlow`-based UI state and `flatMapLatest` for cross-flow composition.
- `affectsMainBalance` flag computed at transaction save time in `ExpenseRepository`, encoding the Liquid Savings/Loan balance rule into each row.

#### Browser emulator (`browser-emulator/index.html`)
- Self-contained single HTML file — no build step, no server. Open directly in any modern browser.
- Full feature parity with the Android app for all four screens.
- `localStorage` persistence under key `expenseiq_v2`.
- Canvas-drawn pie chart with per-category colours.
- Export JSON backup and import JSON backup from the More tab.
- Clear All Data option with confirmation.
- Automatic data migration: legacy account group type names (WALLET, SPENDING, CREDIT_CARD, OTHER) are normalised to OTHERS on load.

[Unreleased]: https://github.com/somrikbanerjee/ExpenseIQ/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/somrikbanerjee/ExpenseIQ/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/somrikbanerjee/ExpenseIQ/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/somrikbanerjee/ExpenseIQ/releases/tag/v1.0.0
