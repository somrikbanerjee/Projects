package com.somrik.expenseiq.presentation.screens.transactions

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import com.somrik.expenseiq.data.db.entity.CategoryEntity
import com.somrik.expenseiq.data.db.entity.TransactionEntity
import com.somrik.expenseiq.presentation.viewmodel.TransactionViewModel
import com.somrik.expenseiq.ui.theme.*
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AddEditTransactionScreen(
    transactionId: Long? = null,
    defaultAccountId: Long? = null,
    onDone: () -> Unit,
    viewModel: TransactionViewModel = hiltViewModel()
) {
    val state by viewModel.uiState.collectAsState()

    var type by remember { mutableStateOf("EXPENSE") }
    var amount by remember { mutableStateOf("") }
    var note by remember { mutableStateOf("") }
    var selectedDate by remember { mutableStateOf(LocalDate.now()) }
    var selectedCategoryId by remember { mutableStateOf<Long?>(null) }
    var selectedAccountId by remember { mutableStateOf(defaultAccountId ?: state.allAccounts.firstOrNull()?.id) }
    var selectedToAccountId by remember { mutableStateOf<Long?>(null) }
    var showDatePicker by remember { mutableStateOf(false) }

    LaunchedEffect(transactionId, state.allAccounts) {
        if (transactionId != null && transactionId != 0L) {
            // editing: not implemented for brevity, would load tx by id
        }
        if (selectedAccountId == null) {
            selectedAccountId = state.allAccounts.firstOrNull()?.id
        }
    }

    val filteredCategories = state.allCategories.filter { it.type == type }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(if (transactionId != null && transactionId != 0L) "Edit Transaction" else "Add Transaction") },
                navigationIcon = {
                    IconButton(onClick = onDone) { Icon(Icons.Default.Close, "Cancel") }
                },
                actions = {
                    TextButton(onClick = {
                        val amtDouble = amount.toDoubleOrNull() ?: return@TextButton
                        val accId = selectedAccountId ?: return@TextButton
                        val dateMs = selectedDate.atStartOfDay(ZoneId.systemDefault()).toInstant().toEpochMilli()
                        viewModel.saveTransaction(
                            TransactionEntity(
                                id = transactionId ?: 0L,
                                date = dateMs,
                                amount = amtDouble,
                                type = type,
                                categoryId = selectedCategoryId,
                                accountId = accId,
                                toAccountId = if (type == "TRANSFER") selectedToAccountId else null,
                                note = note
                            )
                        )
                        onDone()
                    }) { Text("Save", fontWeight = FontWeight.Bold) }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = SurfaceWhite)
            )
        }
    ) { padding ->
        Column(
            Modifier
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // Type selector
            Row(
                Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(12.dp))
                    .background(BackgroundLight),
            ) {
                listOf("INCOME", "EXPENSE", "TRANSFER").forEach { t ->
                    val selected = type == t
                    Box(
                        Modifier
                            .weight(1f)
                            .clip(RoundedCornerShape(12.dp))
                            .background(if (selected) when(t) {
                                "INCOME" -> IncomeBlue
                                "EXPENSE" -> ExpenseRed
                                else -> MaterialTheme.colorScheme.primary
                            } else Color.Transparent)
                            .clickable { type = t; selectedCategoryId = null }
                            .padding(vertical = 12.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            t.lowercase().replaceFirstChar { it.uppercase() },
                            color = if (selected) Color.White else TextSecondary,
                            fontWeight = if (selected) FontWeight.Bold else FontWeight.Normal,
                            fontSize = 14.sp
                        )
                    }
                }
            }

            // Amount
            OutlinedTextField(
                value = amount,
                onValueChange = { amount = it },
                label = { Text("Amount (₹)") },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                leadingIcon = { Text("₹", fontWeight = FontWeight.Bold, fontSize = 18.sp, modifier = Modifier.padding(start = 4.dp)) },
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(12.dp)
            )

            // Date
            OutlinedCard(
                onClick = { showDatePicker = true },
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(12.dp)
            ) {
                Row(
                    Modifier.padding(16.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Icon(Icons.Default.CalendarToday, null, tint = TextSecondary)
                    Text(selectedDate.format(DateTimeFormatter.ofPattern("dd MMM yyyy")))
                }
            }

            // Account selector
            Text("Account", fontWeight = FontWeight.SemiBold, color = TextSecondary, fontSize = 13.sp)
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                items(state.allAccounts) { acc ->
                    val sel = selectedAccountId == acc.id
                    FilterChip(
                        selected = sel,
                        onClick = { selectedAccountId = acc.id },
                        label = { Text(acc.name, fontSize = 13.sp) },
                        colors = FilterChipDefaults.filterChipColors(
                            selectedContainerColor = MaterialTheme.colorScheme.primary,
                            selectedLabelColor = Color.White
                        )
                    )
                }
            }

            // To Account (for transfers)
            if (type == "TRANSFER") {
                Text("To Account", fontWeight = FontWeight.SemiBold, color = TextSecondary, fontSize = 13.sp)
                LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    items(state.allAccounts.filter { it.id != selectedAccountId }) { acc ->
                        val sel = selectedToAccountId == acc.id
                        FilterChip(
                            selected = sel,
                            onClick = { selectedToAccountId = acc.id },
                            label = { Text(acc.name, fontSize = 13.sp) },
                            colors = FilterChipDefaults.filterChipColors(
                                selectedContainerColor = IncomeBlue,
                                selectedLabelColor = Color.White
                            )
                        )
                    }
                }
            }

            // Category (not for transfers)
            if (type != "TRANSFER" && filteredCategories.isNotEmpty()) {
                Text("Category", fontWeight = FontWeight.SemiBold, color = TextSecondary, fontSize = 13.sp)
                CategoryGrid(filteredCategories, selectedCategoryId) { selectedCategoryId = it }
            }

            // Note
            OutlinedTextField(
                value = note,
                onValueChange = { note = it },
                label = { Text("Note (optional)") },
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(12.dp),
                maxLines = 3
            )
        }
    }

    if (showDatePicker) {
        val datePickerState = rememberDatePickerState(
            initialSelectedDateMillis = selectedDate
                .atStartOfDay(ZoneId.systemDefault()).toInstant().toEpochMilli()
        )
        DatePickerDialog(
            onDismissRequest = { showDatePicker = false },
            confirmButton = {
                TextButton(onClick = {
                    datePickerState.selectedDateMillis?.let { ms ->
                        selectedDate = Instant.ofEpochMilli(ms).atZone(ZoneId.systemDefault()).toLocalDate()
                    }
                    showDatePicker = false
                }) { Text("OK") }
            },
            dismissButton = { TextButton(onClick = { showDatePicker = false }) { Text("Cancel") } }
        ) { DatePicker(state = datePickerState) }
    }
}

@Composable
private fun CategoryGrid(
    categories: List<CategoryEntity>,
    selected: Long?,
    onSelect: (Long) -> Unit
) {
    val chunked = categories.chunked(4)
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        chunked.forEach { row ->
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                row.forEach { cat ->
                    val isSelected = selected == cat.id
                    Column(
                        Modifier
                            .weight(1f)
                            .clip(RoundedCornerShape(12.dp))
                            .background(if (isSelected) Color(cat.colorHex.toInt()).copy(alpha = 0.15f) else BackgroundLight)
                            .border(
                                width = if (isSelected) 2.dp else 0.dp,
                                color = if (isSelected) Color(cat.colorHex.toInt()) else Color.Transparent,
                                shape = RoundedCornerShape(12.dp)
                            )
                            .clickable { onSelect(cat.id) }
                            .padding(8.dp),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        Icon(
                            categoryIcon(cat.icon),
                            null,
                            tint = Color(cat.colorHex.toInt()),
                            modifier = Modifier.size(24.dp)
                        )
                        Spacer(Modifier.height(4.dp))
                        Text(
                            cat.name,
                            fontSize = 10.sp,
                            maxLines = 1,
                            color = if (isSelected) Color(cat.colorHex.toInt()) else TextPrimary
                        )
                    }
                }
                repeat(4 - row.size) { Spacer(Modifier.weight(1f)) }
            }
        }
    }
}
