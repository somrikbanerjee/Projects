package com.somrik.expenseiq.domain.model

enum class AccountGroupType {
    OTHERS,
    LIQUID_SAVINGS,
    INVESTMENTS,
    LOAN;

    /** Loan accounts are shown as liabilities in the net-worth summary. */
    fun isLiability() = this == LOAN

    /**
     * Restricted accounts (Liquid Savings, Investments, Loan) only contribute
     * to the monthly income/expense total when transferring to/from an OTHERS account.
     */
    fun hasRestrictedBalanceTracking() = this == LIQUID_SAVINGS || this == INVESTMENTS || this == LOAN

    companion object {
        /** Normalises legacy type names that may be stored in an older database. */
        fun fromString(value: String): AccountGroupType = when (value) {
            "WALLET", "SPENDING", "CREDIT_CARD", "OTHER" -> OTHERS
            else -> runCatching { valueOf(value) }.getOrDefault(OTHERS)
        }
    }
}
