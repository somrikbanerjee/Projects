package com.somrik.expenseiq.presentation.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.somrik.expenseiq.data.db.entity.*
import com.somrik.expenseiq.data.repository.ExpenseRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.YearMonth
import java.time.ZoneId
import javax.inject.Inject

data class DayGroup(
    val date: LocalDate,
    val dayIncome: Double,
    val dayExpense: Double,
    val transactions: List<TransactionWithMeta>
)

data class TransactionWithMeta(
    val transaction: TransactionEntity,
    val category: CategoryEntity?,
    val account: AccountEntity?,
    val toAccount: AccountEntity?
)

data class TransactionUiState(
    val selectedMonth: YearMonth = YearMonth.now(),
    val monthlyIncome: Double = 0.0,
    val monthlyExpense: Double = 0.0,
    val dayGroups: List<DayGroup> = emptyList(),
    val allCategories: List<CategoryEntity> = emptyList(),
    val allAccounts: List<AccountEntity> = emptyList(),
    val allGroups: List<AccountGroupEntity> = emptyList(),
    val searchQuery: String = ""
)

@OptIn(ExperimentalCoroutinesApi::class)
@HiltViewModel
class TransactionViewModel @Inject constructor(
    private val repo: ExpenseRepository
) : ViewModel() {

    private val _selectedMonth = MutableStateFlow(YearMonth.now())
    val selectedMonth: StateFlow<YearMonth> = _selectedMonth.asStateFlow()

    private val _searchQuery = MutableStateFlow("")
    val searchQuery: StateFlow<String> = _searchQuery.asStateFlow()

    val uiState: StateFlow<TransactionUiState> = combine(
        _selectedMonth,
        _searchQuery,
        repo.getAllGroups(),
        repo.getAllAccounts(),
        repo.getAllCategories()
    ) { month, query, groups, accounts, categories ->
        val groupsAndAccounts = groups to accounts
        repo.getTransactionsForMonth(month).map { txList ->
            val filteredList = if (query.isBlank()) {
                txList
            } else {
                txList.filter { tx ->
                    tx.note.contains(query, ignoreCase = true) ||
                            categories.find { it.id == tx.categoryId }?.name?.contains(query, ignoreCase = true) == true
                }
            }
            buildUiState(month, filteredList, categories, accounts, groups, query)
        }
    }.flatMapLatest { it }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), TransactionUiState())

    private fun buildUiState(
        month: YearMonth,
        txList: List<TransactionEntity>,
        categories: List<CategoryEntity>,
        accounts: List<AccountEntity>,
        groups: List<AccountGroupEntity>,
        query: String = ""
    ): TransactionUiState {
        val catMap = categories.associateBy { it.id }
        val accMap = accounts.associateBy { it.id }

        val zone = ZoneId.systemDefault()
        val withMeta = txList.map { tx ->
            TransactionWithMeta(
                transaction = tx,
                category = tx.categoryId?.let { catMap[it] },
                account = accMap[tx.accountId],
                toAccount = tx.toAccountId?.let { accMap[it] }
            )
        }

        val dayGroups = withMeta
            .groupBy { LocalDate.ofInstant(java.time.Instant.ofEpochMilli(it.transaction.date), zone) }
            .entries
            .sortedByDescending { it.key }
            .map { (date, items) ->
                DayGroup(
                    date = date,
                    dayIncome = items.filter { it.transaction.type == "INCOME" }.sumOf { it.transaction.amount },
                    dayExpense = items.filter { it.transaction.type == "EXPENSE" }.sumOf { it.transaction.amount },
                    transactions = items
                )
            }

        val groupMap = groups.associateBy { it.id }

        var income  = txList.filter { it.type == "INCOME"  && it.affectsMainBalance }.sumOf { it.amount }
        var expense = txList.filter { it.type == "EXPENSE" && it.affectsMainBalance }.sumOf { it.amount }

        // Qualifying transfers (Restricted ↔ Spending) count toward monthly totals.
        // Restricted → Spending = income; Spending → Restricted = expense.
        txList.filter { it.type == "TRANSFER" && it.affectsMainBalance }.forEach { tx ->
            val fromGroup = accMap[tx.accountId]?.groupId?.let { groupMap[it] }
            val fromType  = fromGroup?.type?.let { com.somrik.expenseiq.domain.model.AccountGroupType.fromString(it) }
            if (fromType?.hasRestrictedBalanceTracking() == true) income  += tx.amount
            else                                                   expense += tx.amount
        }

        return TransactionUiState(
            selectedMonth = month,
            monthlyIncome = income,
            monthlyExpense = expense,
            dayGroups = dayGroups,
            allCategories = categories,
            allAccounts = accounts,
            allGroups = groups,
            searchQuery = query
        )
    }

    fun setSearchQuery(query: String) {
        _searchQuery.value = query
    }

    fun previousMonth() { _selectedMonth.value = _selectedMonth.value.minusMonths(1) }
    fun nextMonth() { _selectedMonth.value = _selectedMonth.value.plusMonths(1) }

    fun saveTransaction(transaction: TransactionEntity) = viewModelScope.launch {
        repo.saveTransaction(transaction)
    }

    fun deleteTransaction(transaction: TransactionEntity) = viewModelScope.launch {
        repo.deleteTransaction(transaction)
    }
}
