package com.somrik.expenseiq.presentation.screens.accounts

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import com.somrik.expenseiq.data.db.entity.AccountGroupEntity
import com.somrik.expenseiq.domain.model.AccountGroupType
import com.somrik.expenseiq.presentation.screens.transactions.formatCurrency
import com.somrik.expenseiq.presentation.viewmodel.AccountViewModel
import com.somrik.expenseiq.presentation.viewmodel.AccountWithBalance
import com.somrik.expenseiq.presentation.viewmodel.GroupWithAccounts
import com.somrik.expenseiq.ui.theme.*

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AccountsScreen(
    onAccountClick: (Long) -> Unit,
    viewModel: AccountViewModel = hiltViewModel()
) {
    val state by viewModel.accountsUiState.collectAsState()
    var showAddAccountDialog by remember { mutableStateOf(false) }
    var showAddGroupDialog by remember { mutableStateOf(false) }
    var showManageGroupMenu by remember { mutableStateOf(false) }
    var errorMessage by remember { mutableStateOf<String?>(null) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Accounts", fontWeight = FontWeight.Bold) },
                actions = {
                    Box {
                        IconButton(onClick = { showManageGroupMenu = true }) {
                            Icon(Icons.Default.MoreVert, "More")
                        }
                        DropdownMenu(
                            expanded = showManageGroupMenu,
                            onDismissRequest = { showManageGroupMenu = false }
                        ) {
                        DropdownMenuItem(
                            text = { Text("Add Account") },
                            onClick = {
                                if (state.groups.isEmpty()) {
                                    errorMessage = "Please add an account group first."
                                } else {
                                    showAddAccountDialog = true
                                }
                                showManageGroupMenu = false
                            },
                            leadingIcon = { Icon(Icons.Default.AccountBalance, null) }
                        )
                            DropdownMenuItem(
                                text = { Text("Add Group") },
                                onClick = {
                                    showAddGroupDialog = true; showManageGroupMenu = false
                                },
                                leadingIcon = { Icon(Icons.Default.CreateNewFolder, null) }
                            )
                        }
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
                .fillMaxSize()
        ) {
            item {
                // Net worth summary
                Row(
                    Modifier
                        .fillMaxWidth()
                        .background(MaterialTheme.colorScheme.surface)
                        .padding(horizontal = 16.dp, vertical = 14.dp)
                        .height(IntrinsicSize.Min),
                    horizontalArrangement = Arrangement.SpaceEvenly
                ) {
                    NetWorthItem("Assets", state.totalAssets, IncomeBlue)
                    VerticalDivider(modifier = Modifier.fillMaxHeight().padding(vertical = 4.dp), color = MaterialTheme.colorScheme.outlineVariant)
                    NetWorthItem("Liabilities", state.totalLiabilities, ExpenseRed)
                    VerticalDivider(modifier = Modifier.fillMaxHeight().padding(vertical = 4.dp), color = MaterialTheme.colorScheme.outlineVariant)
                    NetWorthItem("Total", state.totalAssets - state.totalLiabilities, MaterialTheme.colorScheme.onSurface)
                }
                HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
                Spacer(Modifier.height(8.dp))
            }

            items(state.groups) { group ->
                AccountGroupSection(group, onAccountClick) { acc ->
                    viewModel.deleteAccount(acc.account)
                }
                Spacer(Modifier.height(8.dp))
            }
            item { Spacer(Modifier.height(80.dp)) }
        }
    }

    if (showAddAccountDialog) {
        AddAccountDialog(
            groups = state.groups.map { it.group },
            onDismiss = { showAddAccountDialog = false },
            onAdd = { name, groupId, defaultBal ->
                viewModel.addAccount(name, groupId, defaultBal)
                showAddAccountDialog = false
            }
        )
    }

    if (showAddGroupDialog) {
        AddGroupDialog(
            onDismiss = { showAddGroupDialog = false },
            onAdd = { name, type ->
                viewModel.addGroup(name, type)
                showAddGroupDialog = false
            }
        )
    }

    if (errorMessage != null) {
        AlertDialog(
            onDismissRequest = { errorMessage = null },
            title = { Text("Information") },
            text = { Text(errorMessage!!) },
            confirmButton = {
                TextButton(onClick = { errorMessage = null }) { Text("OK") }
            }
        )
    }
}

@Composable
private fun NetWorthItem(label: String, amount: Double, color: Color) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(label, fontSize = 12.sp, color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f), modifier = Modifier.alpha(0f))
        Text(formatCurrency(amount), color = color, fontWeight = FontWeight.SemiBold, fontSize = 16.sp)
    }
}

@Composable
private fun AccountGroupSection(
    group: GroupWithAccounts,
    onAccountClick: (Long) -> Unit,
    onDeleteAccount: (AccountWithBalance) -> Unit
) {
    val isLiability = group.groupType.isLiability()

    Column(
        Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surface)
    ) {
        Row(
            Modifier
                .fillMaxWidth()
                .background(MaterialTheme.colorScheme.background)
                .padding(horizontal = 16.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                group.group.name,
                color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.6f),
                fontSize = 13.sp,
                fontWeight = FontWeight.Medium
            )
            Text(
                formatCurrency(group.accounts.sumOf { it.balance }),
                color = if (isLiability) ExpenseRed else IncomeBlue,
                fontSize = 13.sp,
                fontWeight = FontWeight.Medium
            )
        }

        group.accounts.forEach { accBal ->
            var showDeleteConfirm by remember { mutableStateOf(false) }
            AccountRow(
                accBal,
                onClick = { onAccountClick(accBal.account.id) },
                onLongClick = { showDeleteConfirm = true }
            )
            if (showDeleteConfirm) {
                AlertDialog(
                    onDismissRequest = { showDeleteConfirm = false },
                    title = { Text("Delete ${accBal.account.name}?") },
                    text = { Text("This will also delete all transactions for this account.") },
                    confirmButton = {
                        TextButton(onClick = { onDeleteAccount(accBal); showDeleteConfirm = false }) {
                            Text("Delete", color = ExpenseRed)
                        }
                    },
                    dismissButton = {
                        TextButton(onClick = { showDeleteConfirm = false }) { Text("Cancel") }
                    }
                )
            }
        }
    }
}

@Composable
private fun AccountRow(
    accBal: AccountWithBalance,
    onClick: () -> Unit,
    onLongClick: () -> Unit
) {
    Row(
        Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(accBal.account.name, Modifier.weight(1f), fontSize = 14.sp, color = MaterialTheme.colorScheme.onSurface)
        Text(
            formatCurrency(accBal.balance),
            color = if (accBal.balance < 0) ExpenseRed else IncomeBlue,
            fontWeight = FontWeight.Medium,
            fontSize = 14.sp
        )
        Spacer(Modifier.width(8.dp))
        Icon(
            Icons.Default.DragIndicator,
            null,
            tint = MaterialTheme.colorScheme.outlineVariant,
            modifier = Modifier.size(20.dp)
        )
    }
    HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant, modifier = Modifier.padding(horizontal = 16.dp))
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AddAccountDialog(
    groups: List<AccountGroupEntity>,
    onDismiss: () -> Unit,
    onAdd: (String, Long, Double) -> Unit
) {
    var name by remember { mutableStateOf("") }
    var defaultBal by remember { mutableStateOf("") }
    var selectedGroupId by remember { mutableStateOf(groups.firstOrNull()?.id ?: 0L) }
    var expanded by remember { mutableStateOf(false) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Add Account") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it },
                    label = { Text("Account name") },
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(8.dp),
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedTextColor = MaterialTheme.colorScheme.onSurface,
                        unfocusedTextColor = MaterialTheme.colorScheme.onSurface
                    )
                )
                OutlinedTextField(
                    value = defaultBal,
                    onValueChange = { defaultBal = it },
                    label = { Text("Opening balance (₹)") },
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(8.dp),
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedTextColor = MaterialTheme.colorScheme.onSurface,
                        unfocusedTextColor = MaterialTheme.colorScheme.onSurface
                    )
                )
                ExposedDropdownMenuBox(
                    expanded = expanded,
                    onExpandedChange = { expanded = !expanded }
                ) {
                    OutlinedTextField(
                        value = groups.find { it.id == selectedGroupId }?.name ?: "",
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Group") },
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded) },
                        modifier = Modifier
                            .fillMaxWidth()
                            .menuAnchor(),
                        shape = RoundedCornerShape(8.dp),
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedTextColor = MaterialTheme.colorScheme.onSurface,
                            unfocusedTextColor = MaterialTheme.colorScheme.onSurface
                        )
                    )
                    ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
                        groups.forEach { g ->
                            DropdownMenuItem(
                                text = { Text(g.name) },
                                onClick = { selectedGroupId = g.id; expanded = false }
                            )
                        }
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = {
                if (name.isNotBlank()) onAdd(name, selectedGroupId, defaultBal.toDoubleOrNull() ?: 0.0)
            }) { Text("Add") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } }
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AddGroupDialog(
    onDismiss: () -> Unit,
    onAdd: (String, AccountGroupType) -> Unit
) {
    var name by remember { mutableStateOf("") }
    var selectedType by remember { mutableStateOf(AccountGroupType.OTHERS) }
    var expanded by remember { mutableStateOf(false) }
    val typeOptions = listOf(
        AccountGroupType.OTHERS        to "Others",
        AccountGroupType.LIQUID_SAVINGS to "Liquid Savings",
        AccountGroupType.INVESTMENTS    to "Investments",
        AccountGroupType.LOAN           to "Loan"
    )

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Add Account Group") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it },
                    label = { Text("Group name") },
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(8.dp),
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedTextColor = MaterialTheme.colorScheme.onSurface,
                        unfocusedTextColor = MaterialTheme.colorScheme.onSurface
                    )
                )
                ExposedDropdownMenuBox(
                    expanded = expanded,
                    onExpandedChange = { expanded = !expanded }
                ) {
                    OutlinedTextField(
                        value = typeOptions.first { it.first == selectedType }.second,
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Type") },
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded) },
                        modifier = Modifier
                            .fillMaxWidth()
                            .menuAnchor(),
                        shape = RoundedCornerShape(8.dp),
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedTextColor = MaterialTheme.colorScheme.onSurface,
                            unfocusedTextColor = MaterialTheme.colorScheme.onSurface
                        )
                    )
                    ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
                        typeOptions.forEach { (type, label) ->
                            DropdownMenuItem(
                                text = { Text(label) },
                                onClick = { selectedType = type; expanded = false }
                            )
                        }
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = { if (name.isNotBlank()) onAdd(name, selectedType) }) { Text("Add") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } }
    )
}
