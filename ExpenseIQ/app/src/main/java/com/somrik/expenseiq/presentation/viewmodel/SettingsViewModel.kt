package com.somrik.expenseiq.presentation.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.somrik.expenseiq.data.db.entity.AccountEntity
import com.somrik.expenseiq.data.db.entity.AccountGroupEntity
import com.somrik.expenseiq.data.db.entity.CategoryEntity
import com.somrik.expenseiq.data.db.entity.TransactionEntity
import com.somrik.expenseiq.data.pref.SettingsManager
import com.somrik.expenseiq.data.pref.ThemeMode
import com.somrik.expenseiq.data.repository.ExpenseRepository
import com.google.gson.Gson
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

data class BackupData(
    val categories: List<CategoryEntity>,
    val groups: List<AccountGroupEntity>,
    val accounts: List<AccountEntity>,
    val transactions: List<TransactionEntity>
)

@HiltViewModel
class SettingsViewModel @Inject constructor(
    private val repo: ExpenseRepository,
    private val settingsManager: SettingsManager
) : ViewModel() {

    private val gson = Gson()

    val themeMode: StateFlow<ThemeMode> = settingsManager.themeMode

    fun setThemeMode(mode: ThemeMode) {
        settingsManager.setThemeMode(mode)
    }

    val uiState: StateFlow<SettingsUiState> = combine(
        repo.getAllCategories(),
        repo.getAllGroups()
    ) { categories, groups ->
        SettingsUiState(categories, groups)
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), SettingsUiState())

    fun deleteCategory(category: CategoryEntity) = viewModelScope.launch {
        repo.deleteCategory(category)
    }

    fun addCategory(name: String, type: String, icon: String, colorHex: Long) = viewModelScope.launch {
        repo.insertCategory(CategoryEntity(name = name, type = type, icon = icon, colorHex = colorHex))
    }

    fun deleteGroup(group: AccountGroupEntity) = viewModelScope.launch {
        repo.deleteGroup(group)
    }

    fun addGroup(name: String, type: String) = viewModelScope.launch {
        repo.insertGroup(AccountGroupEntity(name = name, type = type))
    }

    fun updateCategoryOrder(categories: List<CategoryEntity>) = viewModelScope.launch {
        categories.forEachIndexed { index, category ->
            repo.updateCategory(category.copy(sortOrder = index))
        }
    }

    fun updateGroupOrder(groups: List<AccountGroupEntity>) = viewModelScope.launch {
        groups.forEachIndexed { index, group ->
            repo.updateGroup(group.copy(sortOrder = index))
        }
    }

    fun clearAllData() = viewModelScope.launch {
        repo.deleteAllTransactions()
        repo.deleteAllAccounts()
        repo.deleteAllGroups()
        repo.deleteAllCategories()
    }

    suspend fun exportBackup(): String {
        val backup = BackupData(
            categories = repo.getAllCategoriesList(),
            groups = repo.getAllGroupsList(),
            accounts = repo.getAllAccountsList(),
            transactions = repo.getAllTransactions()
        )
        return gson.toJson(backup)
    }

    fun importBackup(json: String) = viewModelScope.launch {
        try {
            val backup = gson.fromJson(json, BackupData::class.java)
            repo.deleteAllTransactions()
            repo.deleteAllAccounts()
            repo.deleteAllGroups()
            repo.deleteAllCategories()

            repo.insertCategories(backup.categories)
            repo.insertGroups(backup.groups)
            repo.insertAccounts(backup.accounts)
            repo.insertTransactions(backup.transactions)
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }
}
