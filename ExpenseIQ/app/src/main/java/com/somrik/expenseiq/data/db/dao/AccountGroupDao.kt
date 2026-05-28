package com.somrik.expenseiq.data.db.dao

import androidx.room.*
import com.somrik.expenseiq.data.db.entity.AccountGroupEntity
import kotlinx.coroutines.flow.Flow

@Dao
interface AccountGroupDao {
    @Query("SELECT * FROM account_groups ORDER BY sortOrder ASC")
    fun getAllGroups(): Flow<List<AccountGroupEntity>>

    @Query("SELECT * FROM account_groups WHERE id = :id")
    suspend fun getGroupById(id: Long): AccountGroupEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(group: AccountGroupEntity): Long

    @Update
    suspend fun update(group: AccountGroupEntity)

    @Delete
    suspend fun delete(group: AccountGroupEntity)
}
