# ExpenseIQ

A personal finance tracker for Android with a companion browser emulator for testing. Tracks income, expenses, and transfers across multiple account groups, with special balance-tracking rules for savings and loan accounts.

---

## Features

### Transactions
- Log **Income**, **Expense**, and **Transfer** entries with date, amount, category, account, and note
- Daily-grouped transaction list with per-day income/expense subtotals
- Monthly navigation — balances carry over automatically between months
- Tap any transaction to edit or delete it

### Stats
- Monthly pie chart broken down by category
- Toggle between Expense and Income views
- Transfers that qualify as income/expense (see Balance Rules below) appear as a "Transfer" slice

### Accounts
- Accounts are organised into **Account Groups**, each with a type that controls balance behaviour
- Tap an account to see its own transaction history and monthly summary
- Account balances include an optional **opening balance** that is not counted in the monthly income/expense totals

### Categories
- Separate category lists for Income and Expense
- Pre-seeded with common categories (Food, Transport, Salary, etc.)
- Add, edit, and delete custom categories from the More tab

---

## Account Group Types

| Type | Balance behaviour |
|---|---|
| **Others** | All income/expense transactions count toward the monthly total. This is the default for wallets, bank accounts, credit cards, etc. |
| **Liquid Savings** | Only transfers to/from an **Others** account affect the monthly total. Internal transactions (e.g. interest earned) are tracked in the account balance but do not appear in monthly income/expense. |
| **Investments** | Same rules as Liquid Savings. |
| **Loan** | Same rules as Liquid Savings. Loan accounts are counted as **liabilities** in the net-worth summary. Transfers from a Loan account to an Others account count as income (disbursement); transfers from Others to Loan count as expense (repayment). |

### Why this matters

If you transfer ₹10,000 from your savings (Liquid Savings) to your current account (Others), that ₹10,000 shows up as **income** for the month — because money entered your spending pool. Conversely, moving money into savings shows as an **expense**. Direct credits (salary, cashback) to Others accounts always count normally.

---

## Project Structure

```
ExpenseIQ/
├── app/                          # Android application
│   └── src/main/java/com/somrik/expenseiq/
│       ├── data/
│       │   ├── db/               # Room entities and DAOs
│       │   └── repository/       # ExpenseRepository
│       ├── di/                   # Hilt dependency injection
│       ├── domain/model/         # Enums: AccountGroupType, TransactionType, CategoryType
│       ├── presentation/
│       │   ├── navigation/       # Compose navigation graph
│       │   ├── screens/          # Composable screens
│       │   └── viewmodel/        # TransactionViewModel, AccountViewModel, StatsViewModel
│       └── ui/theme/             # Color, Type, Theme
├── browser-emulator/
│   └── index.html                # Self-contained browser prototype (no server needed)
├── build.gradle.kts
└── settings.gradle.kts
```

---

## Android App

### Tech stack

| Layer | Library |
|---|---|
| UI | Jetpack Compose + Material 3 |
| Navigation | Compose Navigation |
| Database | Room (SQLite) |
| Dependency injection | Hilt |
| Architecture | MVVM + Repository |
| Language | Kotlin |
| Min SDK | 26 (Android 8) |
| Target SDK | 35 (Android 15) |

### Building & running

1. Open the `ExpenseIQ/` folder in **Android Studio** (Hedgehog or newer).
2. Let Gradle sync finish (first run downloads ~300 MB of dependencies).
3. Create an emulator: **Tools → Device Manager → Create Virtual Device** → Pixel 7 → API 35.
4. Press **Run ▶** — the app installs and launches on the virtual device.

The database is seeded with default account groups and categories on first launch. No data migration is needed between versions — Room handles schema versioning.

### Database location

Room stores the SQLite database at the standard Android app-private path. It is not accessible without root or a backup extraction.

---

## Browser Emulator

A single self-contained HTML file that replicates the app's UI and logic in any modern browser. No server, no build step — just open the file.

```
open browser-emulator/index.html
```

**Data** is stored in `localStorage` under the key `expenseiq_v2`.  
**Dark mode** switches automatically when the OS/browser switches.

### Emulator features

- Full transaction CRUD (add, edit, delete)
- Account and group management including deletion
- Stats screen with Canvas-drawn pie chart
- Export/import JSON backup from the More tab
- Supports all four account group types with correct balance logic

---

## Balance Calculation Reference

### Monthly income/expense total (Transactions screen)

```
income  = Σ INCOME transactions where affectsMainBalance = true
        + Σ TRANSFER transactions (Restricted → Others) where affectsMainBalance = true

expense = Σ EXPENSE transactions where affectsMainBalance = true
        + Σ TRANSFER transactions (Others → Restricted) where affectsMainBalance = true
```

`affectsMainBalance` is computed at save time in `ExpenseRepository.enrichAffectsMainBalance()` (Android) and `computeAffectsBalance()` (browser emulator).

### Net worth (Accounts screen)

```
assets      = Σ max(balance, 0) for all non-Loan accounts
liabilities = Σ balance for all Loan accounts
net worth   = assets − liabilities
```

Account balance = `defaultBalance` + net of all income/expense/transfer transactions for that account.
