package com.somrik.expenseiq.data.db.entity

import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(
    tableName = "transactions",
    foreignKeys = [
        ForeignKey(
            entity = AccountEntity::class,
            parentColumns = ["id"],
            childColumns = ["accountId"],
            onDelete = ForeignKey.CASCADE
        )
    ],
    indices = [Index("accountId"), Index("toAccountId"), Index("date")]
)
data class TransactionEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val date: Long,
    val amount: Double,
    val type: String,
    val categoryId: Long? = null,
    val accountId: Long,
    val toAccountId: Long? = null,
    val note: String = "",
    /**
     * False for transactions in LIQUID_SAVINGS/LOAN accounts that don't involve
     * a SPENDING account — those don't appear in the monthly income/expense totals.
     */
    val affectsMainBalance: Boolean = true
)
