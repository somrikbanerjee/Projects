package com.somrik.expenseiq.di

import android.content.Context
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.sqlite.db.SupportSQLiteDatabase
import com.somrik.expenseiq.data.db.AppDatabase
import com.somrik.expenseiq.data.db.dao.*
import com.somrik.expenseiq.data.db.entity.*
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object DatabaseModule {

    @Provides
    @Singleton
    fun provideDatabase(@ApplicationContext context: Context): AppDatabase {
        return Room.databaseBuilder(context, AppDatabase::class.java, "expenseiq.db")
            .fallbackToDestructiveMigration()
            .addCallback(object : RoomDatabase.Callback() {
                override fun onCreate(db: SupportSQLiteDatabase) {
                    super.onCreate(db)
                    CoroutineScope(Dispatchers.IO).launch {
                        seedDatabase(db)
                    }
                }
            })
            .build()
    }

    private fun seedDatabase(db: SupportSQLiteDatabase) {
        // Seed default account groups
        val groups = listOf(
            Triple("Wallets", "OTHERS", 0),
            Triple("Spending Accounts", "OTHERS", 1),
            Triple("Credit Cards", "OTHERS", 2),
            Triple("Liquid Savings", "LIQUID_SAVINGS", 3),
            Triple("Loan", "LOAN", 4)
        )
        groups.forEach { (name, type, order) ->
            db.execSQL(
                "INSERT INTO account_groups (name, type, sortOrder, isSystem) VALUES (?, ?, ?, 1)",
                arrayOf(name, type, order)
            )
        }

        // Seed default expense categories (colors stored as ARGB Long)
        val expenseCategories = listOf(
            Triple("Food", "restaurant", 0xFFFF5722L),
            Triple("Transport", "directions_car", 0xFF2196F3L),
            Triple("Shopping", "shopping_bag", 0xFFE91E63L),
            Triple("Healthcare", "favorite", 0xFFF44336L),
            Triple("Home", "home", 0xFF9C27B0L),
            Triple("Entertainment", "sports_esports", 0xFFFF9800L),
            Triple("Groceries", "shopping_cart", 0xFF4CAF50L),
            Triple("Travel", "flight", 0xFF03A9F4L),
            Triple("Investment", "trending_up", 0xFF8BC34AL),
            Triple("Education", "school", 0xFF607D8BL),
            Triple("Other", "more_horiz", 0xFF9E9E9EL)
        )
        expenseCategories.forEachIndexed { i, (name, icon, color) ->
            db.execSQL(
                "INSERT INTO categories (name, type, icon, colorHex, isSystem) VALUES (?, 'EXPENSE', ?, ?, 1)",
                arrayOf(name, icon, color)
            )
        }

        // Seed default income categories
        val incomeCategories = listOf(
            Triple("Salary", "work", 0xFF4CAF50L),
            Triple("Freelance", "computer", 0xFF00BCD4L),
            Triple("Interest", "savings", 0xFF8BC34AL),
            Triple("Cashback", "monetization_on", 0xFFFFC107L),
            Triple("Investment Return", "trending_up", 0xFF2196F3L),
            Triple("Other", "more_horiz", 0xFF9E9E9EL)
        )
        incomeCategories.forEach { (name, icon, color) ->
            db.execSQL(
                "INSERT INTO categories (name, type, icon, colorHex, isSystem) VALUES (?, 'INCOME', ?, ?, 1)",
                arrayOf(name, icon, color)
            )
        }
    }

    @Provides fun provideGroupDao(db: AppDatabase): AccountGroupDao = db.accountGroupDao()
    @Provides fun provideAccountDao(db: AppDatabase): AccountDao = db.accountDao()
    @Provides fun provideCategoryDao(db: AppDatabase): CategoryDao = db.categoryDao()
    @Provides fun provideTransactionDao(db: AppDatabase): TransactionDao = db.transactionDao()
}
