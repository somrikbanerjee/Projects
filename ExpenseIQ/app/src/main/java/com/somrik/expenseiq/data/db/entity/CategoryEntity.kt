package com.somrik.expenseiq.data.db.entity

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "categories")
data class CategoryEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val name: String,
    val type: String,
    val icon: String = "attach_money",
    val colorHex: Long = 0xFF4CAF50.toLong(),
    val isSystem: Boolean = false
)
