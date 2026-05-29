package com.somrik.expenseiq.presentation.screens.more

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import com.somrik.expenseiq.data.pref.ThemeMode
import com.somrik.expenseiq.presentation.viewmodel.SettingsViewModel
import com.somrik.expenseiq.ui.theme.*
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MoreScreen(
    onManageCategories: () -> Unit,
    onManageGroups: () -> Unit,
    viewModel: SettingsViewModel = hiltViewModel()
) {
    val state by viewModel.uiState.collectAsState()
    val themeMode by viewModel.themeMode.collectAsState()
    var showClearDataDialog by remember { mutableStateOf(false) }
    var showThemeDialog by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val context = LocalContext.current

    val exportLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.CreateDocument("application/json")
    ) { uri ->
        uri?.let {
            scope.launch {
                val json = viewModel.exportBackup()
                context.contentResolver.openOutputStream(it)?.use { os ->
                    os.write(json.toByteArray())
                }
            }
        }
    }

    val importLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.GetContent()
    ) { uri ->
        uri?.let {
            val json = context.contentResolver.openInputStream(it)?.bufferedReader()?.use { it.readText() }
            if (json != null) {
                viewModel.importBackup(json)
            }
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("More", fontWeight = FontWeight.Bold) },
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
                .background(MaterialTheme.colorScheme.background)
        ) {
            item {
                SectionHeader("Appearance")
                SettingsItem(
                    icon = Icons.Default.Palette,
                    iconColor = AccentOrange,
                    label = "Theme",
                    value = when(themeMode) {
                        ThemeMode.LIGHT -> "Light"
                        ThemeMode.DARK -> "Dark"
                        ThemeMode.SYSTEM -> "System Default"
                    },
                    onClick = { showThemeDialog = true }
                )
                Spacer(Modifier.height(8.dp))
            }

            item {
                SectionHeader("Manage")
                SettingsItem(
                    icon = Icons.Default.Label,
                    iconColor = Color(0xFF9C27B0),
                    label = "Categories",
                    value = state.categories.size.toString(),
                    onClick = onManageCategories
                )
                HorizontalDivider(modifier = Modifier.padding(start = 56.dp), color = MaterialTheme.colorScheme.outlineVariant)
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
                    onClick = { exportLauncher.launch("expenseiq_backup.json") }
                )
                HorizontalDivider(modifier = Modifier.padding(start = 56.dp), color = MaterialTheme.colorScheme.outlineVariant)
                SettingsItem(
                    icon = Icons.Default.FileUpload,
                    iconColor = Color(0xFF2196F3),
                    label = "Import Backup",
                    onClick = { importLauncher.launch("application/json") }
                )
                HorizontalDivider(modifier = Modifier.padding(start = 56.dp), color = MaterialTheme.colorScheme.outlineVariant)
                SettingsItem(
                    icon = Icons.Default.DeleteForever,
                    iconColor = Color(0xFFF44336),
                    label = "Clear All Data",
                    labelColor = Color(0xFFF44336),
                    onClick = { showClearDataDialog = true }
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

    if (showClearDataDialog) {
        AlertDialog(
            onDismissRequest = { showClearDataDialog = false },
            title = { Text("Clear All Data?", color = MaterialTheme.colorScheme.onSurface) },
            text = { Text("This will permanently delete all your transactions, accounts, and custom categories. This action cannot be undone.", color = MaterialTheme.colorScheme.onSurface) },
            confirmButton = {
                TextButton(
                    onClick = {
                        viewModel.clearAllData()
                        showClearDataDialog = false
                    }
                ) {
                    Text("Clear All", color = Color(0xFFF44336))
                }
            },
            dismissButton = {
                TextButton(onClick = { showClearDataDialog = false }) {
                    Text("Cancel", color = MaterialTheme.colorScheme.primary)
                }
            },
            containerColor = MaterialTheme.colorScheme.surface
        )
    }

    if (showThemeDialog) {
        AlertDialog(
            onDismissRequest = { showThemeDialog = false },
            title = { Text("Choose Theme", color = MaterialTheme.colorScheme.onSurface) },
            text = {
                Column {
                    ThemeOption("Light", themeMode == ThemeMode.LIGHT) {
                        viewModel.setThemeMode(ThemeMode.LIGHT)
                        showThemeDialog = false
                    }
                    ThemeOption("Dark", themeMode == ThemeMode.DARK) {
                        viewModel.setThemeMode(ThemeMode.DARK)
                        showThemeDialog = false
                    }
                    ThemeOption("System Default", themeMode == ThemeMode.SYSTEM) {
                        viewModel.setThemeMode(ThemeMode.SYSTEM)
                        showThemeDialog = false
                    }
                }
            },
            confirmButton = {},
            dismissButton = {
                TextButton(onClick = { showThemeDialog = false }) {
                    Text("Cancel", color = MaterialTheme.colorScheme.primary)
                }
            },
            containerColor = MaterialTheme.colorScheme.surface
        )
    }
}

@Composable
private fun ThemeOption(
    label: String,
    selected: Boolean,
    onClick: () -> Unit
) {
    Row(
        Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        RadioButton(selected = selected, onClick = onClick)
        Spacer(Modifier.width(8.dp))
        Text(label, color = MaterialTheme.colorScheme.onSurface)
    }
}

@Composable
private fun SectionHeader(title: String) {
    Text(
        text = title.uppercase(),
        modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp),
        fontSize = 11.sp,
        fontWeight = FontWeight.Bold,
        color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.6f),
        letterSpacing = 1.sp
    )
}

@Composable
private fun SettingsItem(
    icon: ImageVector,
    iconColor: Color,
    label: String,
    labelColor: Color = MaterialTheme.colorScheme.onSurface,
    value: String? = null,
    onClick: () -> Unit
) {
    Row(
        Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.surface)
            .clickable(onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 14.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Icon(icon, null, tint = iconColor, modifier = Modifier.size(24.dp))
        Spacer(Modifier.width(16.dp))
        Text(label, Modifier.weight(1f), color = labelColor, fontSize = 15.sp)
        if (value != null) {
            Text(value, color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f), fontSize = 13.sp, modifier = Modifier.padding(horizontal = 8.dp))
        }
        Icon(Icons.Default.ChevronRight, null, tint = MaterialTheme.colorScheme.outlineVariant, modifier = Modifier.size(20.dp))
    }
}
