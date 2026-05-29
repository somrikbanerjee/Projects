package com.somrik.expenseiq.data.repository

import com.somrik.expenseiq.data.db.dao.*
import com.somrik.expenseiq.data.db.entity.*
import com.somrik.expenseiq.domain.model.AccountGroupType
import com.somrik.expenseiq.domain.model.TransactionType
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import java.time.LocalDate
import java.time.YearMonth
import java.time.ZoneId
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class ExpenseRepository @Inject constructor(
    private val accountGroupDao: AccountGroupDao,
    private val accountDao: AccountDao,
    private val categoryDao: CategoryDao,
    private val transactionDao: TransactionDao
) {
    // --- Groups ---
    fun getAllGroups(): Flow<List<AccountGroupEntity>> = accountGroupDao.getAllGroups()
    suspend fun insertGroup(group: AccountGroupEntity): Long = accountGroupDao.insert(group)
    suspend fun updateGroup(group: AccountGroupEntity) = accountGroupDao.update(group)
    suspend fun deleteGroup(group: AccountGroupEntity) = accountGroupDao.delete(group)
    suspend fun deleteAllGroups() = accountGroupDao.deleteAll()

    // --- Accounts ---
    fun getAllAccounts(): Flow<List<AccountEntity>> = accountDao.getAllAccounts()
    fun getAccountsByGroup(groupId: Long): Flow<List<AccountEntity>> = accountDao.getAccountsByGroup(groupId)
    suspend fun insertAccount(account: AccountEntity): Long = accountDao.insert(account)
    suspend fun updateAccount(account: AccountEntity) = accountDao.update(account)
    suspend fun deleteAccount(account: AccountEntity) = accountDao.delete(account)
    suspend fun deleteAllAccounts() = accountDao.deleteAll()

    suspend fun getAccountBalance(accountId: Long): Double {
        val account = accountDao.getAccountById(accountId) ?: return 0.0
        val net = transactionDao.getNetBalanceForAccount(accountId) ?: 0.0
        return account.defaultBalance + net
    }

    // --- Categories ---
    fun getAllCategories(): Flow<List<CategoryEntity>> = categoryDao.getAllCategories()
    fun getCategoriesByType(type: String): Flow<List<CategoryEntity>> = categoryDao.getCategoriesByType(type)
    suspend fun insertCategory(category: CategoryEntity): Long = categoryDao.insert(category)
    suspend fun updateCategory(category: CategoryEntity) = categoryDao.update(category)
    suspend fun deleteCategory(category: CategoryEntity) = categoryDao.delete(category)
    suspend fun deleteAllCategories() = categoryDao.deleteAll()

    // --- Transactions ---
    fun getTransactionsForMonth(yearMonth: YearMonth): Flow<List<TransactionEntity>> {
        val (start, end) = yearMonth.toEpochRange()
        return transactionDao.getTransactionsForMonth(start, end)
    }

    fun getTransactionsForAccount(accountId: Long): Flow<List<TransactionEntity>> =
        transactionDao.getTransactionsForAccount(accountId)

    fun getTransactionsForAccountInMonth(accountId: Long, yearMonth: YearMonth): Flow<List<TransactionEntity>> {
        val (start, end) = yearMonth.toEpochRange()
        return transactionDao.getTransactionsForAccountInMonth(accountId, start, end)
    }

    suspend fun getTransactionById(id: Long): TransactionEntity? = transactionDao.getTransactionById(id)

    suspend fun saveTransaction(transaction: TransactionEntity) {
        val enriched = enrichAffectsMainBalance(transaction)
        if (enriched.id == 0L) transactionDao.insert(enriched)
        else transactionDao.update(enriched)
    }

    suspend fun deleteTransaction(transaction: TransactionEntity) = transactionDao.delete(transaction)
    suspend fun deleteTransactionById(id: Long) = transactionDao.deleteById(id)
    suspend fun deleteAllTransactions() = transactionDao.deleteAll()

    // --- Backup ---
    suspend fun getAllTransactions(): List<TransactionEntity> = transactionDao.getAllTransactions()
    suspend fun insertTransactions(list: List<TransactionEntity>) = list.forEach { transactionDao.insert(it) }

    suspend fun getAllCategoriesList(): List<CategoryEntity> = categoryDao.getAllCategoriesList()
    suspend fun insertCategories(list: List<CategoryEntity>) = list.forEach { categoryDao.insert(it) }

    suspend fun getAllAccountsList(): List<AccountEntity> = accountDao.getAllAccountsList()
    suspend fun insertAccounts(list: List<AccountEntity>) = list.forEach { accountDao.insert(it) }

    suspend fun getAllGroupsList(): List<AccountGroupEntity> = accountGroupDao.getAllGroupsList()
    suspend fun insertGroups(list: List<AccountGroupEntity>) = list.forEach { accountGroupDao.insert(it) }

    /**
     * Computes affectsMainBalance:
     * - Non-transfers in LIQUID_SAVINGS/LOAN accounts never affect the monthly total.
     * - Transfers only affect it when one side is LIQUID_SAVINGS/LOAN and the other
     *   is SPENDING (either direction).
     * - All other transactions in non-restricted accounts always affect the total.
     */
    private suspend fun enrichAffectsMainBalance(tx: TransactionEntity): TransactionEntity {
        val groups = accountGroupDao.getAllGroups().first().associateBy { it.id }

        suspend fun groupTypeOf(accountId: Long): AccountGroupType? {
            val account = accountDao.getAccountById(accountId) ?: return null
            val group = groups[account.groupId] ?: return null
            return AccountGroupType.fromString(group.type)
        }

        val fromType = groupTypeOf(tx.accountId) ?: return tx.copy(affectsMainBalance = true)

        if (tx.type != TransactionType.TRANSFER.name) {
            return tx.copy(affectsMainBalance = !fromType.hasRestrictedBalanceTracking())
        }

        // Transfer: only affects balance when Restricted ↔ Spending
        val toType = tx.toAccountId?.let { groupTypeOf(it) }
            ?: return tx.copy(affectsMainBalance = false)

        val affects = (fromType.hasRestrictedBalanceTracking() && toType == AccountGroupType.OTHERS) ||
                      (fromType == AccountGroupType.OTHERS && toType.hasRestrictedBalanceTracking())
        return tx.copy(affectsMainBalance = affects)
    }

    suspend fun getMonthlyTotals(yearMonth: YearMonth): Pair<Double, Double> {
        val (start, end) = yearMonth.toEpochRange()
        val income = transactionDao.getTotalIncomeForMonth(start, end) ?: 0.0
        val expense = transactionDao.getTotalExpenseForMonth(start, end) ?: 0.0
        return income to expense
    }

    private fun YearMonth.toEpochRange(): Pair<Long, Long> {
        val zone = ZoneId.systemDefault()
        val start = atDay(1).atStartOfDay(zone).toInstant().toEpochMilli()
        val end = atEndOfMonth().plusDays(1).atStartOfDay(zone).toInstant().toEpochMilli()
        return start to end
    }
}
