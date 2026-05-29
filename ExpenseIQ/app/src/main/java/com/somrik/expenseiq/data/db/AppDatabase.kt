package com.somrik.expenseiq.data.db

import androidx.room.Database
import androidx.room.RoomDatabase
import com.somrik.expenseiq.data.db.dao.*
import com.somrik.expenseiq.data.db.entity.*

@Database(
    entities = [
        AccountGroupEntity::class,
        AccountEntity::class,
        CategoryEntity::class,
        TransactionEntity::class
    ],
    version = 2,
    exportSchema = false
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun accountGroupDao(): AccountGroupDao
    abstract fun accountDao(): AccountDao
    abstract fun categoryDao(): CategoryDao
    abstract fun transactionDao(): TransactionDao
}
