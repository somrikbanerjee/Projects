package com.somrik.expenseiq.presentation.screens.accounts

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import com.somrik.expenseiq.presentation.screens.transactions.DaySection
import com.somrik.expenseiq.presentation.screens.transactions.formatCurrency
import com.somrik.expenseiq.presentation.viewmodel.AccountViewModel
import com.somrik.expenseiq.ui.theme.*
import java.time.format.DateTimeFormatter

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AccountDetailScreen(
    accountId: Long,
    onBack: () -> Unit,
    onAddTransaction: (Long) -> Unit,
    onEditTransaction: (Long) -> Unit,
    viewModel: AccountViewModel = hiltViewModel()
) {
    LaunchedEffect(accountId) { viewModel.setDetailAccount(accountId) }
    val state by viewModel.accountDetailState.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text(state.account?.name ?: "", fontWeight = FontWeight.Bold)
                        Text(
                            formatCurrency(state.balance),
                            fontSize = 13.sp,
                            color = if (state.balance >= 0) IncomeBlue else ExpenseRed
                        )
                    }
                },
                navigationIcon = {
                    IconButton(onClick = onBack) { Icon(Icons.Default.ArrowBack, "Back") }
                },
                actions = {
                    IconButton(onClick = viewModel::detailPreviousMonth) {
                        Icon(Icons.Default.ChevronLeft, "Prev")
                    }
                    Text(
                        state.selectedMonth.format(DateTimeFormatter.ofPattern("MMM yyyy")),
                        fontWeight = FontWeight.SemiBold, fontSize = 14.sp,
                        modifier = Modifier.padding(vertical = 4.dp)
                    )
                    IconButton(onClick = viewModel::detailNextMonth) {
                        Icon(Icons.Default.ChevronRight, "Next")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = SurfaceWhite)
            )
        },
        floatingActionButton = {
            FloatingActionButton(
                onClick = { onAddTransaction(accountId) },
                containerColor = ExpenseRed,
                contentColor = Color.White
            ) { Icon(Icons.Default.Add, "Add") }
        }
    ) { padding ->
        Column(Modifier.padding(padding)) {
            // Monthly summary
            Row(
                Modifier
                    .fillMaxWidth()
                    .background(SurfaceWhite)
                    .padding(horizontal = 16.dp, vertical = 12.dp)
                    .height(IntrinsicSize.Min),
                horizontalArrangement = Arrangement.SpaceEvenly
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text("Income", fontSize = 12.sp, color = TextSecondary)
                    Text(formatCurrency(state.monthlyIncome), color = IncomeBlue, fontWeight = FontWeight.SemiBold)
                }
                VerticalDivider(modifier = Modifier.fillMaxHeight().padding(vertical = 4.dp))
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text("Expenses", fontSize = 12.sp, color = TextSecondary)
                    Text(formatCurrency(state.monthlyExpense), color = ExpenseRed, fontWeight = FontWeight.SemiBold)
                }
                VerticalDivider(modifier = Modifier.fillMaxHeight().padding(vertical = 4.dp))
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    val total = state.monthlyIncome - state.monthlyExpense
                    Text("Total", fontSize = 12.sp, color = TextSecondary)
                    Text(formatCurrency(total), color = if (total >= 0) IncomeBlue else ExpenseRed, fontWeight = FontWeight.SemiBold)
                }
            }
            HorizontalDivider(color = DividerGray)

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
