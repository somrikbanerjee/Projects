package com.somrik.expenseiq.presentation.screens.stats

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChevronLeft
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import com.somrik.expenseiq.presentation.screens.transactions.formatCurrency
import com.somrik.expenseiq.presentation.viewmodel.CategoryStat
import com.somrik.expenseiq.presentation.viewmodel.StatsViewModel
import com.somrik.expenseiq.ui.theme.*
import java.time.format.DateTimeFormatter

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StatsScreen(viewModel: StatsViewModel = hiltViewModel()) {
    val state by viewModel.uiState.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        IconButton(onClick = viewModel::previousMonth) { Icon(Icons.Default.ChevronLeft, "Prev") }
                        Text(
                            state.selectedMonth.format(DateTimeFormatter.ofPattern("MMM yyyy")),
                            fontWeight = FontWeight.Bold, fontSize = 18.sp
                        )
                        IconButton(onClick = viewModel::nextMonth) { Icon(Icons.Default.ChevronRight, "Next") }
                    }
                },
                actions = {
                    TextButton(onClick = viewModel::toggleMode) {
                        Text(
                            if (state.showExpenses) "Monthly ▾" else "Income ▾",
                            color = MaterialTheme.colorScheme.onSurface
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.surface),
                windowInsets = WindowInsets(0, 0, 0, 0)
            )
        },
        containerColor = MaterialTheme.colorScheme.background
    ) { padding ->
        LazyColumn(
            Modifier
                .padding(padding)
                .fillMaxSize(),
            verticalArrangement = Arrangement.spacedBy(0.dp)
        ) {
            item {
                // Income / Expense header
                Row(
                    Modifier
                        .fillMaxWidth()
                        .background(MaterialTheme.colorScheme.surface)
                        .padding(horizontal = 16.dp, vertical = 8.dp),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Text(
                        "Income ${formatCurrency(state.totalIncome)}",
                        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
                        fontSize = 13.sp
                    )
                    Text(
                        "Expenses ${formatCurrency(state.totalExpense)}",
                        fontWeight = FontWeight.SemiBold,
                        color = MaterialTheme.colorScheme.onSurface,
                        fontSize = 13.sp
                    )
                }
                HorizontalDivider(thickness = 2.dp, color = ExpenseRed)
            }

            item {
                // Pie chart
                if (state.categoryStats.isNotEmpty()) {
                    Box(
                        Modifier
                            .fillMaxWidth()
                            .height(280.dp)
                            .padding(16.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        PieChart(state.categoryStats)
                        PieChartLabels(state.categoryStats)
                    }
                } else {
                    Box(
                        Modifier
                            .fillMaxWidth()
                            .height(200.dp),
                        contentAlignment = Alignment.Center
                    ) { Text("No data for this period", color = TextSecondary) }
                }
            }

            itemsIndexed(state.categoryStats) { index, stat ->
                CategoryStatRow(stat, index)
            }
            item { Spacer(Modifier.height(80.dp)) }
        }
    }
}

@Composable
private fun PieChart(stats: List<CategoryStat>) {
    val colors = ChartColors
    Canvas(
        Modifier
            .size(200.dp)
    ) {
        var startAngle = -90f
        stats.forEachIndexed { i, stat ->
            val sweep = stat.percentage / 100f * 360f
            drawArc(
                color = colors[i % colors.size],
                startAngle = startAngle,
                sweepAngle = sweep,
                useCenter = true,
                topLeft = Offset(0f, 0f),
                size = Size(size.width, size.height)
            )
            startAngle += sweep
        }
    }
}

@Composable
private fun PieChartLabels(stats: List<CategoryStat>) {
    // Surrounding labels — simplified to legend below chart
}

@Composable
private fun CategoryStatRow(stat: CategoryStat, index: Int) {
    val color = ChartColors[index % ChartColors.size]

    Row(
        Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surface)
            .padding(horizontal = 16.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Box(
            Modifier
                .size(40.dp)
                .clip(RoundedCornerShape(8.dp))
                .background(
                    stat.category?.let { Color(it.colorHex.toInt()) } ?: MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f)
                ),
            contentAlignment = Alignment.Center
        ) {
            Text(
                "${stat.percentage.toInt()}%",
                color = Color.White,
                fontSize = 11.sp,
                fontWeight = FontWeight.Bold
            )
        }
        Text(
            stat.category?.name ?: "Uncategorized",
            Modifier.weight(1f),
            fontWeight = FontWeight.Medium,
            fontSize = 15.sp,
            color = MaterialTheme.colorScheme.onSurface
        )
        Text(
            formatCurrency(stat.amount),
            fontWeight = FontWeight.SemiBold,
            fontSize = 15.sp,
            color = MaterialTheme.colorScheme.onSurface
        )
    }
    HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant, modifier = Modifier.padding(horizontal = 16.dp))
}
