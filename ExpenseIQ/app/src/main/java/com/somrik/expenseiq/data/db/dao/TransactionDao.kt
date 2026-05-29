package com.somrik.expenseiq.data.db.dao

import androidx.room.*
import com.somrik.expenseiq.data.db.entity.TransactionEntity
import kotlinx.coroutines.flow.Flow

@Dao
interface TransactionDao {
    @Query("""
        SELECT * FROM transactions
        WHERE date >= :startMs AND date < :endMs
        ORDER BY date DESC
    """)
    fun getTransactionsForMonth(startMs: Long, endMs: Long): Flow<List<TransactionEntity>>

    @Query("""
        SELECT * FROM transactions
        WHERE (accountId = :accountId OR toAccountId = :accountId)
        ORDER BY date DESC
    """)
    fun getTransactionsForAccount(accountId: Long): Flow<List<TransactionEntity>>

    @Query("""
        SELECT * FROM transactions
        WHERE (accountId = :accountId OR toAccountId = :accountId)
        AND date >= :startMs AND date < :endMs
        ORDER BY date DESC
    """)
    fun getTransactionsForAccountInMonth(accountId: Long, startMs: Long, endMs: Long): Flow<List<TransactionEntity>>

    @Query("SELECT * FROM transactions WHERE id = :id")
    suspend fun getTransactionById(id: Long): TransactionEntity?

    @Query("""
        SELECT SUM(amount) FROM transactions
        WHERE type = 'INCOME' AND affectsMainBalance = 1
        AND date >= :startMs AND date < :endMs
    """)
    suspend fun getTotalIncomeForMonth(startMs: Long, endMs: Long): Double?

    @Query("""
        SELECT SUM(amount) FROM transactions
        WHERE type = 'EXPENSE' AND affectsMainBalance = 1
        AND date >= :startMs AND date < :endMs
    """)
    suspend fun getTotalExpenseForMonth(startMs: Long, endMs: Long): Double?

    @Query("""
        SELECT SUM(
            CASE
                WHEN type = 'INCOME' THEN amount
                WHEN type = 'EXPENSE' THEN -amount
                ELSE 0
            END
        ) FROM transactions
        WHERE accountId = :accountId AND date < :beforeMs
    """)
    suspend fun getNetBalanceForAccountBefore(accountId: Long, beforeMs: Long): Double?

    @Query("""
        SELECT SUM(
            CASE
                WHEN type = 'INCOME' THEN amount
                WHEN type = 'EXPENSE' THEN -amount
                WHEN type = 'TRANSFER' AND accountId = :accountId THEN -amount
                WHEN type = 'TRANSFER' AND toAccountId = :accountId THEN amount
                ELSE 0
            END
        ) FROM transactions
        WHERE accountId = :accountId OR toAccountId = :accountId
    """)
    suspend fun getNetBalanceForAccount(accountId: Long): Double?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(transaction: TransactionEntity): Long

    @Update
    suspend fun update(transaction: TransactionEntity)

    @Delete
    suspend fun delete(transaction: TransactionEntity)

    @Query("DELETE FROM transactions WHERE id = :id")
    suspend fun deleteById(id: Long)

    @Query("DELETE FROM transactions")
    suspend fun deleteAll()

    @Query("SELECT * FROM transactions")
    suspend fun getAllTransactions(): List<TransactionEntity>
}
