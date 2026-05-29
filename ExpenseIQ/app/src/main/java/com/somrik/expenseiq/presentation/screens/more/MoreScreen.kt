package com.somrik.expenseiq.presentation.screens.more

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import com.somrik.expenseiq.presentation.viewmodel.SettingsViewModel
import com.somrik.expenseiq.ui.theme.*

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MoreScreen(
    onManageCategories: () -> Unit,
    onManageGroups: () -> Unit,
    viewModel: SettingsViewModel = hiltViewModel()
) {
    val state by viewModel.uiState.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("More", fontWeight = FontWeight.Bold) },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = SurfaceWhite),
                windowInsets = WindowInsets(0, 0, 0, 0)
            )
        }
    ) { padding ->
        LazyColumn(
            Modifier
                .padding(padding)
                .fillMaxSize()
                .background(BackgroundLight)
        ) {
            item {
                SectionHeader("Manage")
                SettingsItem(
                    icon = Icons.Default.Label,
                    iconColor = Color(0xFF9C27B0),
                    label = "Categories",
                    value = state.categories.size.toString(),
                    onClick = onManageCategories
                )
                HorizontalDivider(modifier = Modifier.padding(start = 56.dp), color = DividerGray)
                SettingsItem(
                    icon = Icons.Default.GridView,
                    iconColor = Color(0xFF2196F3),
                    label = "Account Groups",
                    value = state.groups.size.toString(),
                    onClick = onManageGroups
                )
                Spacer(Modifier.height(16.dp))
            }

            item {
                SectionHeader("Data")
                SettingsItem(
                    icon = Icons.Default.FileDownload,
                    iconColor = Color(0xFF4CAF50),
                    label = "Export Backup",
                    onClick = { /* Implement export */ }
                )
                HorizontalDivider(modifier = Modifier.padding(start = 56.dp), color = DividerGray)
                SettingsItem(
                    icon = Icons.Default.FileUpload,
                    iconColor = Color(0xFF2196F3),
                    label = "Import Backup",
                    onClick = { /* Implement import */ }
                )
                HorizontalDivider(modifier = Modifier.padding(start = 56.dp), color = DividerGray)
                SettingsItem(
                    icon = Icons.Default.DeleteForever,
                    iconColor = Color(0xFFF44336),
                    label = "Clear All Data",
                    labelColor = Color(0xFFF44336),
                    onClick = { /* Implement clear data */ }
                )
            }

            item {
                Box(
                    Modifier
                        .fillMaxWidth()
                        .padding(32.dp),
                    contentAlignment = Alignment.Center
                ) {
                    Text(
                        "ExpenseIQ · Version 1.0",
                        color = TextSecondary,
                        fontSize = 12.sp
                    )
                }
            }
        }
    }
}

@Composable
private fun SectionHeader(title: String) {
    Text(
        text = title.uppercase(),
        modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp),
        fontSize = 11.sp,
        fontWeight = FontWeight.Bold,
        color = TextSecondary,
        letterSpacing = 1.sp
    )
}

@Composable
private fun SettingsItem(
    icon: ImageVector,
    iconColor: Color,
    label: String,
    labelColor: Color = TextPrimary,
    value: String? = null,
    onClick: () -> Unit
) {
    Row(
        Modifier
            .fillMaxWidth()
            .background(SurfaceWhite)
            .clickable(onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 14.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Icon(icon, null, tint = iconColor, modifier = Modifier.size(24.dp))
        Spacer(Modifier.width(16.dp))
        Text(label, Modifier.weight(1f), color = labelColor, fontSize = 15.sp)
        if (value != null) {
            Text(value, color = TextSecondary, fontSize = 13.sp, modifier = Modifier.padding(horizontal = 8.dp))
        }
        Icon(Icons.Default.ChevronRight, null, tint = DividerGray, modifier = Modifier.size(20.dp))
    }
}
