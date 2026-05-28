package com.somrik.expenseiq.presentation.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.somrik.expenseiq.data.db.entity.*
import com.somrik.expenseiq.data.repository.ExpenseRepository
import com.somrik.expenseiq.domain.model.AccountGroupType
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import java.time.YearMonth
import javax.inject.Inject

data class AccountWithBalance(
    val account: AccountEntity,
    val balance: Double
)

data class GroupWithAccounts(
    val group: AccountGroupEntity,
    val accounts: List<AccountWithBalance>,
    val groupType: AccountGroupType
)

data class AccountsUiState(
    val groups: List<GroupWithAccounts> = emptyList(),
    val totalAssets: Double = 0.0,
    val totalLiabilities: Double = 0.0
)

data class AccountDetailUiState(
    val account: AccountEntity? = null,
    val balance: Double = 0.0,
    val selectedMonth: YearMonth = YearMonth.now(),
    val monthlyIncome: Double = 0.0,
    val monthlyExpense: Double = 0.0,
    val dayGroups: List<DayGroup> = emptyList(),
    val allCategories: List<CategoryEntity> = emptyList(),
    val allAccounts: List<AccountEntity> = emptyList()
)

@HiltViewModel
class AccountViewModel @Inject constructor(
    private val repo: ExpenseRepository
) : ViewModel() {

    val accountsUiState: StateFlow<AccountsUiState> = combine(
        repo.getAllGroups(),
        repo.getAllAccounts()
    ) { groups, accounts -> groups to accounts }
        .flatMapLatest { (groups, accounts) ->
            flow {
                val groupedAccounts = groups.map { group ->
                    val groupType = AccountGroupType.fromString(group.type)
                    val accsInGroup = accounts.filter { it.groupId == group.id }
                    val accsWithBalance = accsInGroup.map { acc ->
                        val bal = repo.getAccountBalance(acc.id)
                        AccountWithBalance(acc, bal)
                    }
                    GroupWithAccounts(group, accsWithBalance, groupType)
                }.filter { it.accounts.isNotEmpty() }

                val assets = groupedAccounts
                    .filter { !it.groupType.isLiability() }
                    .sumOf { g -> g.accounts.sumOf { maxOf(it.balance, 0.0) } }
                val liabilities = groupedAccounts
                    .filter { it.groupType.isLiability() }
                    .sumOf { g -> g.accounts.sumOf { it.balance } }

                emit(AccountsUiState(groupedAccounts, assets, liabilities))
            }
        }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), AccountsUiState())

    // --- Manage Groups ---
    fun addGroup(name: String, type: AccountGroupType) = viewModelScope.launch {
        val existing = accountsUiState.value.groups
        repo.insertGroup(AccountGroupEntity(name = name, type = type.name, sortOrder = existing.size))
    }

    fun updateGroup(group: AccountGroupEntity) = viewModelScope.launch { repo.updateGroup(group) }
    fun deleteGroup(group: AccountGroupEntity) = viewModelScope.launch { repo.deleteGroup(group) }

    // --- Manage Accounts ---
    fun addAccount(name: String, groupId: Long, defaultBalance: Double) = viewModelScope.launch {
        repo.insertAccount(AccountEntity(groupId = groupId, name = name, defaultBalance = defaultBalance))
    }

    fun updateAccount(account: AccountEntity) = viewModelScope.launch { repo.updateAccount(account) }
    fun deleteAccount(account: AccountEntity) = viewModelScope.launch { repo.deleteAccount(account) }

    // --- Account Detail ---
    private val _detailAccountId = MutableStateFlow<Long?>(null)
    private val _detailMonth = MutableStateFlow(YearMonth.now())

    @OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
    val accountDetailState: StateFlow<AccountDetailUiState> = combine(
        _detailAccountId,
        _detailMonth,
        repo.getAllAccounts(),
        repo.getAllCategories()
    ) { id, month, accounts, cats -> Triple(id, month, accounts to cats) }
        .flatMapLatest { (id, month, accsCats) ->
            val (accounts, cats) = accsCats
            if (id == null) return@flatMapLatest flowOf(AccountDetailUiState())
            repo.getTransactionsForAccountInMonth(id, month).map { txList ->
                val account = accounts.find { it.id == id }
                val balance = repo.getAccountBalance(id)
                val catMap = cats.associateBy { it.id }
                val accMap = accounts.associateBy { it.id }
                val zone = java.time.ZoneId.systemDefault()
                val withMeta = txList.map { tx ->
                    TransactionWithMeta(tx, tx.categoryId?.let { catMap[it] }, accMap[tx.accountId], tx.toAccountId?.let { accMap[it] })
                }
                val dayGroups = withMeta
                    .groupBy { java.time.LocalDate.ofInstant(java.time.Instant.ofEpochMilli(it.transaction.date), zone) }
                    .entries.sortedByDescending { it.key }
                    .map { (date, items) ->
                        DayGroup(
                            date = date,
                            dayIncome = items.filter { it.transaction.type == "INCOME" }.sumOf { it.transaction.amount },
                            dayExpense = items.filter { it.transaction.type == "EXPENSE" }.sumOf { it.transaction.amount },
                            transactions = items
                        )
                    }
                val income = txList.filter { it.type == "INCOME" }.sumOf { it.amount }
                val expense = txList.filter { it.type == "EXPENSE" }.sumOf { it.amount }
                AccountDetailUiState(account, balance, month, income, expense, dayGroups, cats, accounts)
            }
        }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), AccountDetailUiState())

    fun setDetailAccount(id: Long) { _detailAccountId.value = id }
    fun detailPreviousMonth() { _detailMonth.value = _detailMonth.value.minusMonths(1) }
    fun detailNextMonth() { _detailMonth.value = _detailMonth.value.plusMonths(1) }
}
