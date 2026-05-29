package com.somrik.expenseiq.presentation.screens.transactions

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import com.somrik.expenseiq.presentation.viewmodel.DayGroup
import com.somrik.expenseiq.presentation.viewmodel.TransactionUiState
import com.somrik.expenseiq.presentation.viewmodel.TransactionViewModel
import com.somrik.expenseiq.presentation.viewmodel.TransactionWithMeta
import com.somrik.expenseiq.ui.theme.*
import java.text.NumberFormat
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TransactionsScreen(
    onAddTransaction: () -> Unit,
    onEditTransaction: (Long) -> Unit,
    viewModel: TransactionViewModel = hiltViewModel()
) {
    val state by viewModel.uiState.collectAsState()
    var isSearching by remember { mutableStateOf(false) }

    Scaffold(
        topBar = {
            MonthHeader(
                state = state,
                onPrev = viewModel::previousMonth,
                onNext = viewModel::nextMonth,
                isSearching = isSearching,
                onSearchToggle = {
                    isSearching = it
                    if (!it) viewModel.setSearchQuery("")
                },
                onSearchQueryChange = viewModel::setSearchQuery
            )
        },
        containerColor = MaterialTheme.colorScheme.background,
        floatingActionButton = {
            FloatingActionButton(
                onClick = onAddTransaction,
                containerColor = ExpenseRed,
                contentColor = Color.White
            ) { Icon(Icons.Default.Add, "Add transaction") }
        }
    ) { padding ->
        Column(Modifier.padding(padding)) {
            MonthSummaryBar(state.monthlyIncome, state.monthlyExpense)
            if (state.dayGroups.isEmpty()) {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text("No transactions this month", color = TextSecondary)
                }
            } else {
                LazyColumn(Modifier.fillMaxSize()) {
                    items(state.dayGroups) { dayGroup ->
                        DaySection(dayGroup, onEditTransaction)
                    }
                    item { Spacer(Modifier.height(80.dp)) }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun MonthHeader(
    state: TransactionUiState,
    onPrev: () -> Unit,
    onNext: () -> Unit,
    isSearching: Boolean,
    onSearchToggle: (Boolean) -> Unit,
    onSearchQueryChange: (String) -> Unit
) {
    TopAppBar(
        title = {
            if (isSearching) {
                TextField(
                    value = state.searchQuery,
                    onValueChange = onSearchQueryChange,
                    modifier = Modifier.fillMaxWidth(),
                    placeholder = { Text("Search transactions...", color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f)) },
                    singleLine = true,
                    colors = TextFieldDefaults.colors(
                        focusedContainerColor = Color.Transparent,
                        unfocusedContainerColor = Color.Transparent,
                        disabledContainerColor = Color.Transparent,
                        focusedIndicatorColor = Color.Transparent,
                        unfocusedIndicatorColor = Color.Transparent,
                        focusedTextColor = MaterialTheme.colorScheme.onSurface,
                        unfocusedTextColor = MaterialTheme.colorScheme.onSurface
                    ),
                    trailingIcon = {
                        IconButton(onClick = { onSearchToggle(false) }) {
                            Icon(Icons.Default.Close, "Close search", tint = MaterialTheme.colorScheme.onSurface)
                        }
                    }
                )
            } else {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.fillMaxHeight()
                ) {
                    IconButton(onClick = onPrev) { Icon(Icons.Default.ChevronLeft, "Previous", tint = MaterialTheme.colorScheme.onSurface) }
                    Text(
                        state.selectedMonth.format(DateTimeFormatter.ofPattern("MMM yyyy")),
                        fontWeight = FontWeight.Bold,
                        fontSize = 18.sp,
                        color = MaterialTheme.colorScheme.onSurface
                    )
                    IconButton(onClick = onNext) { Icon(Icons.Default.ChevronRight, "Next", tint = MaterialTheme.colorScheme.onSurface) }
                }
            }
        },
        actions = {
            if (!isSearching) {
                IconButton(onClick = { onSearchToggle(true) }) {
                    Icon(Icons.Default.Search, "Search", tint = MaterialTheme.colorScheme.onSurface)
                }
            }
        },
        colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.surface),
        windowInsets = WindowInsets(0, 0, 0, 0)
    )
}

@Composable
private fun MonthSummaryBar(income: Double, expense: Double) {
    val total = income - expense
    Row(
        Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surface)
            .padding(horizontal = 16.dp, vertical = 12.dp)
            .height(IntrinsicSize.Min),
        horizontalArrangement = Arrangement.SpaceEvenly
    ) {
        SummaryItem("Income", income, IncomeBlue)
        VerticalDivider(modifier = Modifier.fillMaxHeight().padding(vertical = 4.dp), color = MaterialTheme.colorScheme.outlineVariant)
        SummaryItem("Expenses", expense, ExpenseRed)
        VerticalDivider(modifier = Modifier.fillMaxHeight().padding(vertical = 4.dp), color = MaterialTheme.colorScheme.outlineVariant)
        SummaryItem("Total", total, if (total >= 0) IncomeBlue else ExpenseRed)
    }
    HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
}

@Composable
private fun SummaryItem(label: String, amount: Double, color: Color) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(label, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f))
        Text(
            formatCurrency(amount),
            color = color,
            fontWeight = FontWeight.SemiBold,
            fontSize = 15.sp
        )
    }
}

@Composable
fun DaySection(dayGroup: DayGroup, onEdit: (Long) -> Unit) {
    Column {
        Row(
            Modifier
                .fillMaxWidth()
                .background(MaterialTheme.colorScheme.background)
                .padding(horizontal = 16.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(
                    dayGroup.date.dayOfMonth.toString(),
                    fontWeight = FontWeight.Bold,
                    fontSize = 20.sp,
                    color = MaterialTheme.colorScheme.onBackground
                )
                Surface(
                    color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.6f),
                    shape = RoundedCornerShape(4.dp)
                ) {
                    Text(
                        dayGroup.date.dayOfWeek.name.take(3),
                        Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
                        color = MaterialTheme.colorScheme.background,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.Medium
                    )
                }
                Text(
                    dayGroup.date.format(DateTimeFormatter.ofPattern("MM.yyyy")),
                    color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.6f),
                    fontSize = 12.sp
                )
            }
            Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                if (dayGroup.dayIncome > 0)
                    Text(formatCurrency(dayGroup.dayIncome), color = IncomeBlue, fontSize = 13.sp)
                if (dayGroup.dayExpense > 0)
                    Text(formatCurrency(dayGroup.dayExpense), color = ExpenseRed, fontSize = 13.sp)
            }
        }
        dayGroup.transactions.forEach { txMeta ->
            TransactionRow(txMeta, onEdit)
        }
        HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
    }
}

@Composable
private fun TransactionRow(txMeta: TransactionWithMeta, onEdit: (Long) -> Unit) {
    val tx = txMeta.transaction
    val isIncome = tx.type == "INCOME"
    val isTransfer = tx.type == "TRANSFER"

    Row(
        Modifier
            .fillMaxWidth()
            .clickable { onEdit(tx.id) }
            .background(MaterialTheme.colorScheme.surface)
            .padding(horizontal = 16.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(
            Modifier
                .size(36.dp)
                .clip(CircleShape)
                .background(
                    txMeta.category?.let { Color(it.colorHex.toInt()) }
                        ?: if (isTransfer) IncomeBlue else MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f)
                ),
            contentAlignment = Alignment.Center
        ) {
            Icon(
                imageVector = categoryIcon(txMeta.category?.icon ?: "swap_horiz"),
                contentDescription = null,
                tint = Color.White,
                modifier = Modifier.size(20.dp)
            )
        }
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(
                when {
                    isTransfer -> "Transfer"
                    else -> txMeta.category?.name ?: "Uncategorized"
                },
                fontWeight = FontWeight.Medium,
                fontSize = 14.sp,
                color = MaterialTheme.colorScheme.onSurface
            )
            Text(
                when {
                    isTransfer -> "${txMeta.account?.name ?: ""} → ${txMeta.toAccount?.name ?: ""}"
                    else -> txMeta.account?.name ?: ""
                },
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
                fontSize = 12.sp
            )
            if (tx.note.isNotBlank())
                Text(tx.note, color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f), fontSize = 11.sp)
        }
        Text(
            formatCurrency(tx.amount),
            color = when {
                isIncome -> IncomeBlue
                isTransfer -> MaterialTheme.colorScheme.onSurface
                else -> ExpenseRed
            },
            fontWeight = FontWeight.Medium,
            fontSize = 14.sp
        )
    }
}

fun formatCurrency(amount: Double): String {
    val fmt = NumberFormat.getInstance(Locale("en", "IN"))
    fmt.minimumFractionDigits = 2
    fmt.maximumFractionDigits = 2
    return "₹${fmt.format(amount)}"
}

fun categoryIcon(name: String?) = when (name) {
    "restaurant" -> Icons.Outlined.Restaurant
    "directions_car" -> Icons.Outlined.DirectionsCar
    "shopping_bag" -> Icons.Outlined.ShoppingBag
    "favorite" -> Icons.Outlined.Favorite
    "home" -> Icons.Outlined.Home
    "sports_esports" -> Icons.Outlined.SportsEsports
    "shopping_cart" -> Icons.Outlined.ShoppingCart
    "flight" -> Icons.Outlined.Flight
    "trending_up" -> Icons.Outlined.TrendingUp
    "school" -> Icons.Outlined.School
    "work" -> Icons.Outlined.Work
    "computer" -> Icons.Outlined.Computer
    "savings" -> Icons.Outlined.Savings
    "monetization_on" -> Icons.Outlined.MonetizationOn
    "swap_horiz" -> Icons.Outlined.SwapHoriz
    "attach_money" -> Icons.Outlined.AttachMoney
    else -> Icons.Outlined.MoreHoriz
}
