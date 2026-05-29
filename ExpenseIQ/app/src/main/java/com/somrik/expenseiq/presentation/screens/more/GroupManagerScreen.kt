package com.somrik.expenseiq.presentation.screens.more

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
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import com.somrik.expenseiq.data.db.entity.AccountGroupEntity
import com.somrik.expenseiq.presentation.viewmodel.SettingsViewModel
import com.somrik.expenseiq.ui.theme.*

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun GroupManagerScreen(
    onBack: () -> Unit,
    viewModel: SettingsViewModel = hiltViewModel()
) {
    val state by viewModel.uiState.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Account Groups", fontWeight = FontWeight.Bold) },
                navigationIcon = {
                    IconButton(onClick = onBack) { Icon(Icons.Default.ArrowBack, "Back") }
                },
                actions = {
                    IconButton(onClick = { /* Add group dialog */ }) {
                        Icon(Icons.Default.Add, "Add")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.surface),
                windowInsets = WindowInsets(0, 0, 0, 0)
            )
        },
        containerColor = MaterialTheme.colorScheme.background
    ) { padding ->
        LazyColumn(Modifier.padding(padding).fillMaxSize()) {
            items(state.groups) { group ->
                GroupItem(group) {
                    viewModel.deleteGroup(group)
                }
                HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant, modifier = Modifier.padding(horizontal = 16.dp))
            }
        }
    }
}

@Composable
private fun GroupItem(
    group: AccountGroupEntity,
    onDelete: () -> Unit
) {
    Row(
        Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surface)
            .padding(horizontal = 16.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column(Modifier.weight(1f)) {
            Text(group.name, fontSize = 15.sp, fontWeight = FontWeight.Medium, color = MaterialTheme.colorScheme.onSurface)
            Text(
                group.type,
                fontSize = 12.sp,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
                modifier = Modifier.alpha(0f)
            )
        }
        
        IconButton(onClick = onDelete) {
            Icon(Icons.Default.Delete, "Delete", tint = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f), modifier = Modifier.size(20.dp))
        }
        
        Icon(
            Icons.Default.DragIndicator,
            "Reorder",
            tint = MaterialTheme.colorScheme.outlineVariant,
            modifier = Modifier.size(24.dp).padding(4.dp)
        )
    }
}
