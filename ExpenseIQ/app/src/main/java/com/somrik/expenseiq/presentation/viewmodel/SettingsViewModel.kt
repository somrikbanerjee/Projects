package com.somrik.expenseiq.presentation.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.somrik.expenseiq.data.db.entity.AccountGroupEntity
import com.somrik.expenseiq.data.db.entity.CategoryEntity
import com.somrik.expenseiq.data.repository.ExpenseRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import javax.inject.Inject

data class SettingsUiState(
    val categories: List<CategoryEntity> = emptyList(),
    val groups: List<AccountGroupEntity> = emptyList()
)

@HiltViewModel
class SettingsViewModel @Inject constructor(
    private val repo: ExpenseRepository
) : ViewModel() {

    val uiState: StateFlow<SettingsUiState> = combine(
        repo.getAllCategories(),
        repo.getAllGroups()
    ) { categories, groups ->
        SettingsUiState(categories, groups)
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), SettingsUiState())

    fun deleteCategory(category: CategoryEntity) = viewModelScope.launch {
        repo.deleteCategory(category)
    }

    fun addCategory(name: String, type: String, icon: String, colorHex: String) = viewModelScope.launch {
        repo.insertCategory(CategoryEntity(name = name, type = type, icon = icon, colorHex = colorHex))
    }
}
