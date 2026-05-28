package com.somrik.expenseiq.presentation.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.somrik.expenseiq.data.db.entity.AccountEntity
import com.somrik.expenseiq.data.db.entity.AccountGroupEntity
import com.somrik.expenseiq.data.db.entity.CategoryEntity
import com.somrik.expenseiq.data.db.entity.TransactionEntity
import com.somrik.expenseiq.data.repository.ExpenseRepository
import com.somrik.expenseiq.domain.model.AccountGroupType
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.*
import java.time.YearMonth
import javax.inject.Inject

data class CategoryStat(
    val category: CategoryEntity?,
    val amount: Double,
    val percentage: Float
)

data class StatsUiState(
    val selectedMonth: YearMonth = YearMonth.now(),
    val showExpenses: Boolean = true,
    val totalIncome: Double = 0.0,
    val totalExpense: Double = 0.0,
    val categoryStats: List<CategoryStat> = emptyList()
)

@OptIn(ExperimentalCoroutinesApi::class)
@HiltViewModel
class StatsViewModel @Inject constructor(
    private val repo: ExpenseRepository
) : ViewModel() {

    private val _selectedMonth = MutableStateFlow(YearMonth.now())
    private val _showExpenses = MutableStateFlow(true)

    val uiState: StateFlow<StatsUiState> = combine(
        _selectedMonth, _showExpenses,
        repo.getAllCategories(), repo.getAllAccounts(), repo.getAllGroups()
    ) { month, showExp, cats, accs, groups ->
        arrayOf(month, showExp, cats, accs, groups)
    }.flatMapLatest { arr ->
        @Suppress("UNCHECKED_CAST")
        val month     = arr[0] as YearMonth
        val showExp   = arr[1] as Boolean
        val cats      = arr[2] as List<CategoryEntity>
        val accs      = arr[3] as List<AccountEntity>
        val groups    = arr[4] as List<AccountGroupEntity>
        repo.getTransactionsForMonth(month).map { txList ->
            buildStats(month, showExp, txList, cats, accs, groups)
        }
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), StatsUiState())

    private fun buildStats(
        month: YearMonth,
        showExpenses: Boolean,
        txList: List<TransactionEntity>,
        categories: List<CategoryEntity>,
        accounts: List<AccountEntity>,
        groups: List<AccountGroupEntity>
    ): StatsUiState {
        val catMap   = categories.associateBy { it.id }
        val accMap   = accounts.associateBy { it.id }
        val groupMap = groups.associateBy { it.id }

        fun fromGroupType(tx: TransactionEntity): AccountGroupType? {
            val grp = accMap[tx.accountId]?.groupId?.let { groupMap[it] } ?: return null
            return AccountGroupType.fromString(grp.type)
        }

        var income  = txList.filter { it.type == "INCOME"  && it.affectsMainBalance }.sumOf { it.amount }
        var expense = txList.filter { it.type == "EXPENSE" && it.affectsMainBalance }.sumOf { it.amount }

        // Qualifying transfers count toward totals shown in the header.
        txList.filter { it.type == "TRANSFER" && it.affectsMainBalance }.forEach { tx ->
            if (fromGroupType(tx)?.hasRestrictedBalanceTracking() == true) income  += tx.amount
            else                                                            expense += tx.amount
        }

        // Pie chart data: regular income/expense + qualifying transfers shown as "Transfer".
        val filtered = txList.filter { tx ->
            if (!tx.affectsMainBalance) return@filter false
            when (tx.type) {
                "EXPENSE"  -> showExpenses
                "INCOME"   -> !showExpenses
                "TRANSFER" -> {
                    val fromRestricted = fromGroupType(tx)?.hasRestrictedBalanceTracking() == true
                    if (showExpenses) !fromRestricted else fromRestricted
                }
                else -> false
            }
        }

        val total = filtered.sumOf { it.amount }
        val grouped = filtered.groupBy { if (it.type == "TRANSFER") null else it.categoryId }
        val stats = grouped.entries
            .map { (catId, items) ->
                val amount = items.sumOf { it.amount }
                CategoryStat(
                    category = catId?.let { catMap[it] },
                    amount = amount,
                    percentage = if (total > 0) (amount / total * 100).toFloat() else 0f
                )
            }
            .sortedByDescending { it.amount }

        return StatsUiState(month, showExpenses, income, expense, stats)
    }

    fun previousMonth() { _selectedMonth.value = _selectedMonth.value.minusMonths(1) }
    fun nextMonth() { _selectedMonth.value = _selectedMonth.value.plusMonths(1) }
    fun toggleMode() { _showExpenses.value = !_showExpenses.value }
}
