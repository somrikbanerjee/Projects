package com.somrik.expenseiq.presentation.screens.more

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
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
import com.somrik.expenseiq.data.db.entity.CategoryEntity
import com.somrik.expenseiq.presentation.screens.transactions.categoryIcon
import com.somrik.expenseiq.presentation.viewmodel.SettingsViewModel
import com.somrik.expenseiq.ui.theme.*

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CategoryManagerScreen(
    onBack: () -> Unit,
    viewModel: SettingsViewModel = hiltViewModel()
) {
    val state by viewModel.uiState.collectAsState()
    var selectedType by remember { mutableStateOf("EXPENSE") }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Categories", fontWeight = FontWeight.Bold) },
                navigationIcon = {
                    IconButton(onClick = onBack) { Icon(Icons.Default.ArrowBack, "Back") }
                },
                actions = {
                    IconButton(onClick = { /* Add category dialog */ }) {
                        Icon(Icons.Default.Add, "Add")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = SurfaceWhite),
                windowInsets = WindowInsets(0, 0, 0, 0)
            )
        }
    ) { padding ->
        Column(Modifier.padding(padding).fillMaxSize()) {
            TabRow(
                selectedTabIndex = if (selectedType == "EXPENSE") 0 else 1,
                containerColor = SurfaceWhite,
                contentColor = MaterialTheme.colorScheme.primary
            ) {
                Tab(
                    selected = selectedType == "EXPENSE",
                    onClick = { selectedType = "EXPENSE" },
                    text = { Text("Expenses") }
                )
                Tab(
                    selected = selectedType == "INCOME",
                    onClick = { selectedType = "INCOME" },
                    text = { Text("Income") }
                )
            }

            val categories = state.categories.filter { it.type == selectedType }

            LazyColumn(Modifier.fillMaxSize()) {
                items(categories) { category ->
                    CategoryItem(category) {
                        viewModel.deleteCategory(category)
                    }
                    HorizontalDivider(color = DividerGray, modifier = Modifier.padding(horizontal = 16.dp))
                }
            }
        }
    }
}

@Composable
private fun CategoryItem(
    category: CategoryEntity,
    onDelete: () -> Unit
) {
    Row(
        Modifier
            .fillMaxWidth()
            .background(SurfaceWhite)
            .padding(horizontal = 16.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(
            Modifier
                .size(36.dp)
                .clip(CircleShape)
                .background(Color(category.colorHex.toInt())),
            contentAlignment = Alignment.Center
        ) {
            Icon(
                categoryIcon(category.icon),
                null,
                tint = Color.White,
                modifier = Modifier.size(20.dp)
            )
        }
        Spacer(Modifier.width(12.dp))
        Text(category.name, Modifier.weight(1f), fontSize = 15.sp)
        
        if (!category.isSystem) {
            IconButton(onClick = onDelete) {
                Icon(Icons.Default.Delete, "Delete", tint = TextSecondary, modifier = Modifier.size(20.dp))
            }
        }
    }
}
