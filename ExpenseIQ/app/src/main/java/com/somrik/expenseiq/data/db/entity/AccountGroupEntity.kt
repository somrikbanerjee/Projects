package com.somrik.expenseiq.data.db.entity

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "account_groups")
data class AccountGroupEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val name: String,
    val type: String,
    val sortOrder: Int = 0,
    val isSystem: Boolean = false
)
